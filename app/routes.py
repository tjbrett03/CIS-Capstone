import hmac
import json
import os
import anthropic
import requests
from flask import Blueprint, render_template, request, jsonify, abort, session, redirect, url_for, current_app, flash
from config.goals import GOALS
from config.audiences import AUDIENCES
from app import limiter

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


def generate_narrative(api_key, interview_path, goal, audience):
    """Read the saved interview file and call Claude to produce a finished narrative."""
    with open(interview_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    raw_quotes = data.get("raw_quotes", [])
    if isinstance(raw_quotes, list):
        raw_quotes_str = "; ".join(f'"{q}"' for q in raw_quotes)
    else:
        raw_quotes_str = str(raw_quotes)

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        goal_name=goal["label"],
        audience_name=audience["label"],
        person=data.get("person", ""),
        moment=data.get("moment", ""),
        tension=data.get("tension", ""),
        change=data.get("change", ""),
        outcome=data.get("outcome", ""),
        raw_quotes=raw_quotes_str,
        goal_tone=goal["tone"],
        goal_length=goal["length"],
        goal_priority=goal["priority"],
        audience_level=audience["reading_level"],
        audience_care=audience["values"],
    )

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        system=CLAUDE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return message.content[0].text


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
    # Allow login/logout through without authentication.
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
    )


@main.route("/restart")
def restart():
    # Clear the interview state but keep the user authenticated.
    goal_id = session.get("goal_id")
    audience_id = session.get("audience_id")
    session.pop("messages", None)
    session.pop("completed", None)
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

    # Block further messages once the interview has been completed and JSON extracted.
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
    _is_one_word = len(user_message.split()) <= 2
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
        session["messages"] = messages
        session.modified = True

        # If the reply is valid JSON, treat it as the final extraction and lock the interview.
        # Only mark as completed if the JSON parses successfully — a parse failure means
        # the extraction wasn't saved, so the interview should remain open.
        trimmed = reply.strip()
        if trimmed.startswith("{") and trimmed.endswith("}"):
            try:
                extracted = json.loads(trimmed)
                interview_path = save_extraction(session.sid, {
                    "goal": goal["label"],
                    "audience": audience["label"],
                    **extracted,
                })
                narrative = generate_narrative(
                    current_app.config["ANTHROPIC_API_KEY"],
                    interview_path,
                    goal,
                    audience,
                )
                # Replace the raw JSON in the message history with the narrative.
                messages[-1]["content"] = narrative
                session["messages"] = messages
                session["completed"] = True
                response = {"reply": narrative, "completed": True}
            except json.JSONDecodeError:
                pass  # Malformed JSON from model — don't lock the interview.
                response = {"reply": reply}
        else:
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
    except Exception as e:
        return jsonify({"error": str(e)}), 500
