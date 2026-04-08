import os


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-key-change-me")
    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    DEBUG_CONTEXT = os.environ.get("DEBUG_CONTEXT", "false").lower() == "true"
    SESSION_TYPE = "filesystem"
    SESSION_FILE_DIR = os.path.join(os.path.dirname(__file__), "..", "flask_session")
    SESSION_PERMANENT = False
    LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.7"))
