import json
import os
import requests
from flask import Blueprint, render_template, request, jsonify, abort, session, redirect, url_for, current_app
from config.goals import GOALS
from config.audiences import AUDIENCES

INTERVIEWS_DIR = os.path.join(os.path.dirname(__file__), "..", "interviews")
_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "system_prompt.txt")

with open(_PROMPT_PATH, "r", encoding="utf-8") as _f:
    SYSTEM_PROMPT = _f.read()


def save_extraction(session_id, payload):
    os.makedirs(INTERVIEWS_DIR, exist_ok=True)
    path = os.path.join(INTERVIEWS_DIR, f"interview_{session_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

main = Blueprint("main", __name__)


@main.route("/")
def index():
    return render_template("index.html", goals=GOALS, audiences=AUDIENCES)


OPENING_MESSAGE = "To start, can you tell me a little about the person at the center of this story? You don't need to use their name — just help me picture who they are."


@main.route("/interview")
def interview():
    goal_id = request.args.get("goal") or session.get("goal_id")
    audience_id = request.args.get("audience") or session.get("audience_id")

    if goal_id not in GOALS or audience_id not in AUDIENCES:
        return redirect(url_for("main.index"))

    # Only reset if starting a new interview (goal/audience changed or no existing session)
    if session.get("goal_id") != goal_id or session.get("audience_id") != audience_id:
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
    )


@main.route("/restart")
def restart():
    goal_id = session.get("goal_id")
    audience_id = session.get("audience_id")
    session.clear()
    return redirect(url_for("main.interview", goal=goal_id, audience=audience_id))


@main.route("/export")
def export():
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

    user_message = request.get_json().get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    messages.append({"role": "user", "content": user_message})

    goal = GOALS[goal_id]
    audience = AUDIENCES[audience_id]

    system_content = (SYSTEM_PROMPT
        .replace("{goal_name}", goal["label"])
        .replace("{audience_name}", audience["label"])
        .replace("{goal_priority}", goal["priority"])
        .replace("{audience_level}", audience["reading_level"])
    )

    try:
        resp = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "gemma2:9b",
                "messages": [{"role": "system", "content": system_content}] + messages,
                "stream": False,
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

        trimmed = reply.strip()
        if trimmed.startswith("{") and trimmed.endswith("}"):
            try:
                extracted = json.loads(trimmed)
                save_extraction(session.sid, {
                    "goal": goal["label"],
                    "audience": audience["label"],
                    **extracted,
                })
            except json.JSONDecodeError:
                pass

        response = {"reply": reply}
        if current_app.config.get("DEBUG_CONTEXT"):
            context_window = 8192  # Gemma 2 9B 8k
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
