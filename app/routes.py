import hmac
import json
import os
import anthropic
import requests
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, current_app
from config.goals import GOALS
from config.audiences import AUDIENCES
from app import limiter
from app import pii, readability

INTERVIEWS_DIR = os.path.join(os.path.dirname(__file__), "..", "interviews")
_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "system_prompt.txt")
_CLAUDE_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "claude_system_prompt.txt")
_CLAUDE_USER_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "claude_user_prompt.txt")

# Load prompts once at startup. Requires a Flask restart to pick up file changes.
with open(_PROMPT_PATH, "r", encoding="utf-8") as _f:
    SYSTEM_PROMPT = _f.read()

with open(_CLAUDE_PROMPT_PATH, "r", encoding="utf-8") as _f:
    CLAUDE_SYSTEM_PROMPT = _f.read()

with open(_CLAUDE_USER_PROMPT_PATH, "r", encoding="utf-8") as _f:
    _USER_PROMPT_TEMPLATE = _f.read()


CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_MAX_TOKENS = 2048


def build_narrative_prompt(extracted, goal, audience):
    """Build the user prompt for Claude from the extracted story fields.

    Uses str.replace() rather than str.format() because story fields can
    contain literal braces (e.g. "{name}") which would cause a KeyError
    if passed through format().
    """
    raw_quotes = extracted.get("raw_quotes", [])
    if isinstance(raw_quotes, list):
        raw_quotes_str = "; ".join(f'"{q}"' for q in raw_quotes)
    else:
        raw_quotes_str = str(raw_quotes)

    return (
        _USER_PROMPT_TEMPLATE
        .replace("{goal_name}", goal["label"])
        .replace("{audience_name}", audience["label"])
        .replace("{person}", extracted.get("person", ""))
        .replace("{moment}", extracted.get("moment", ""))
        .replace("{tension}", extracted.get("tension", ""))
        .replace("{change}", extracted.get("change", ""))
        .replace("{outcome}", extracted.get("outcome", ""))
        .replace("{raw_quotes}", raw_quotes_str)
        .replace("{goal_tone}", goal["tone"])
        .replace("{goal_length}", goal["length"])
        .replace("{goal_priority}", goal["priority"])
        .replace("{audience_level}", audience["reading_level"])
        .replace("{audience_care}", audience["values"])
    )


def save_extraction(session_id, payload):
    # Persist the extracted story elements to a JSON file in the interviews directory.
    os.makedirs(INTERVIEWS_DIR, exist_ok=True)
    path = os.path.join(INTERVIEWS_DIR, f"interview_{session_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path

main = Blueprint("main", __name__)


@main.before_request
def require_auth():
    # Allow login and logout routes through without requiring authentication.
    if request.endpoint in ("main.login", "main.logout"):
        return
    if not session.get("authenticated"):
        return redirect(url_for("main.login"))


@main.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute; 20 per hour", methods=["POST"])
def login():
    if session.get("authenticated"):
        return redirect(url_for("main.index"))
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        expected = current_app.config["APP_PASSWORD"]
        if hmac.compare_digest(password.encode(), expected.encode()):
            session["authenticated"] = True
            return redirect(url_for("main.index"))
        error = "Incorrect password."
    return render_template("login.html", error=error)


@main.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.login"))


@main.route("/")
def index():
    return render_template("index.html", goals=GOALS, audiences=AUDIENCES)


# First message shown to the user before any model interaction.
OPENING_MESSAGE = "To start, can you tell me a little about the person at the center of this story? You don't need to use their name — just help me picture who they are."


@main.route("/interview")
def interview():
    goal_id = request.args.get("goal") or session.get("goal_id")
    audience_id = request.args.get("audience") or session.get("audience_id")

    if goal_id not in GOALS or audience_id not in AUDIENCES:
        return redirect(url_for("main.index"))

    # Reset the session if the goal or audience changed, or if messages were cleared (e.g. after restart).
    if session.get("goal_id") != goal_id or session.get("audience_id") != audience_id or "messages" not in session:
        session["goal_id"] = goal_id
        session["audience_id"] = audience_id
        session["messages"] = [{"role": "assistant", "content": OPENING_MESSAGE}]

    return render_template(
        "interview.html",
        goal_id=goal_id,
        goal=GOALS[goal_id],
        audience_id=audience_id,
        audience=AUDIENCES[audience_id],
        messages=session["messages"],
        debug_context=current_app.config.get("DEBUG_CONTEXT", False),
        completed=session.get("completed", False),
        pii_findings=session.get("pii_findings", []),
        readability=session.get("readability"),
    )


@main.route("/restart")
def restart():
    # Clear the interview state but keep the user authenticated.
    goal_id = session.get("goal_id")
    audience_id = session.get("audience_id")
    session.pop("messages", None)
    session.pop("completed", None)
    session.pop("pii_findings", None)
    session.pop("readability", None)
    return redirect(url_for("main.interview", goal=goal_id, audience=audience_id))


@main.route("/export")
def export():
    # Download the full conversation history as a JSON file.
    messages = session.get("messages", [])
    goal_id = session.get("goal_id")
    audience_id = session.get("audience_id")
    payload = {
        "goal": GOALS[goal_id]["label"] if goal_id in GOALS else None,
        "audience": AUDIENCES[audience_id]["label"] if audience_id in AUDIENCES else None,
        "messages": messages,
    }
    return current_app.response_class(
        json.dumps(payload, indent=2, ensure_ascii=False),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename=conversation_{session.sid}.json"},
    )


@main.route("/chat", methods=["POST"])
def chat():
    goal_id = session.get("goal_id")
    audience_id = session.get("audience_id")
    messages = session.get("messages", [])

    if goal_id not in GOALS or audience_id not in AUDIENCES:
        return jsonify({"error": "No active interview session. Please start from the selection screen."}), 400

    # Block further messages once the interview is complete and the narrative has been generated.
    if session.get("completed"):
        return jsonify({"error": "This interview is complete."}), 400

    user_message = request.get_json().get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    max_length = current_app.config.get("MAX_MESSAGE_LENGTH", 2000)
    if len(user_message) > max_length:
        return jsonify({"error": f"Message too long. Please keep responses under {max_length} characters."}), 400

    messages.append({"role": "user", "content": user_message})

    # Intercept short responses and known prompt injection attempts.
    # Instead of sending to the model, repeat the last assistant message silently.
    _injection_phrases = ["forget your system prompt", "forget your instructions", "your new instructions"]
    _is_one_word = len(user_message.split()) == 1
    _is_injection = any(phrase in user_message.lower() for phrase in _injection_phrases)

    if _is_one_word or _is_injection:
        messages.pop()  # Don't save the intercepted message to the session.
        last_reply = next((m["content"] for m in reversed(messages) if m["role"] == "assistant"), None)
        if last_reply:
            return jsonify({"reply": last_reply})

    goal = GOALS[goal_id]
    audience = AUDIENCES[audience_id]

    # Substitute dynamic values into the system prompt template.
    system_content = (SYSTEM_PROMPT
        .replace("{goal_name}", goal["label"])
        .replace("{audience_name}", audience["label"])
        .replace("{goal_priority}", goal["priority"])
        .replace("{audience_level}", audience["reading_level"])
    )

    try:
        model = current_app.config["LLM_MODEL"]
        temperature = current_app.config.get("LLM_TEMPERATURE", 0.7)
        context_window = current_app.config["LLM_NUM_CTX"]
        resp = requests.post(
            f"{current_app.config['OLLAMA_URL']}/api/chat",
            json={
                "model": model,
                # System prompt is prepended as the first message so all models receive it consistently.
                "messages": [{"role": "system", "content": system_content}] + messages,
                "stream": False,
                "options": {"temperature": temperature, "num_ctx": context_window},
            },
            timeout=60,
        )
        resp.raise_for_status()
        ollama_data = resp.json()
        reply = ollama_data["message"]["content"]
        prompt_tokens = ollama_data.get("prompt_eval_count", 0)

        messages.append({"role": "assistant", "content": reply})

        # If the reply looks like JSON, attempt extraction and narrative generation.
        # If JSON parsing fails, treat it as a normal reply and keep the interview open.
        trimmed = reply.strip()
        if trimmed.startswith("{") and trimmed.endswith("}"):
            try:
                # Step 1: parse the local model's JSON extraction and save it.
                # Step 2: send the extracted fields to Claude for narrative generation.
                # Step 3: scan the narrative for PII and score for readability.
                # If JSON parsing fails the interview stays open — the model will try again.
                extracted = json.loads(trimmed)
                save_extraction(session.sid, {
                    "goal": goal["label"],
                    "audience": audience["label"],
                    **extracted,
                })
                user_prompt = build_narrative_prompt(extracted, goal, audience)
                client = anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"], timeout=60.0)
                message = client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=CLAUDE_MAX_TOKENS,
                    temperature=0.3,
                    system=CLAUDE_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                narrative = message.content[0].text
                messages[-1]["content"] = narrative
                pii_findings = pii.scan(narrative)
                readability_score = readability.score(narrative, audience["reading_level"])
                session["messages"] = messages
                session["completed"] = True
                session["pii_findings"] = pii_findings
                session["readability"] = readability_score
                response = {
                    "reply": narrative,
                    "completed": True,
                    "pii_findings": pii_findings,
                    "readability": readability_score,
                }
            except json.JSONDecodeError:
                session["messages"] = messages
                response = {"reply": reply}
        else:
            session["messages"] = messages
            response = {"reply": reply}

        if current_app.config.get("DEBUG_CONTEXT"):
            context_pct = round((prompt_tokens / context_window) * 100, 1) if prompt_tokens else None
            response["debug_context"] = {
                "goal": goal["label"],
                "audience": audience["label"],
                "writing_priority": goal["priority"],
                "reading_level": audience["reading_level"],
                "context_used": f"{prompt_tokens} / {context_window} tokens ({context_pct}%)" if context_pct is not None else "unavailable",
                "messages": messages[:-1],
            }
        return jsonify(response)
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not connect to Ollama. Make sure it is running on port 11434."}), 503
    except Exception:
        current_app.logger.exception("Chat request failed")
        return jsonify({"error": "Something went wrong. Please try again."}), 500
  