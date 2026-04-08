import os


class Config:
    # Used to sign session cookies and CSRF tokens — must be a strong random value in production.
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")
    if not SECRET_KEY:
        raise RuntimeError("FLASK_SECRET_KEY is not set. Add it to your .env file.")

    # Maximum allowed length for a user message in characters.
    MAX_MESSAGE_LENGTH = 2000

    # Enables Flask debug mode and auto-reload on .py file changes.
    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    # When true, shows a debug panel in the interview UI with context usage and message history.
    DEBUG_CONTEXT = os.environ.get("DEBUG_CONTEXT", "false").lower() == "true"

    # Store sessions on the filesystem so large conversation histories fit.
    SESSION_TYPE = "filesystem"
    SESSION_FILE_DIR = os.path.join(os.path.dirname(__file__), "..", "flask_session")
    SESSION_PERMANENT = False

    # Ollama model to use — must be set in .env or the app will fail to start.
    # Pull the model first with: ollama pull <model-name>
    LLM_MODEL = os.environ.get("LLM_MODEL")
    if not LLM_MODEL:
        raise RuntimeError("LLM_MODEL is not set. Add it to your .env file (e.g. LLM_MODEL=llama3.1:8b).")

    # Base URL for the local Ollama instance. Change this if Ollama is running on a different host or port.
    OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

    # Token context window passed to Ollama. Controls how much of the conversation
    # history the model can see. Larger values use more VRAM.
    LLM_NUM_CTX = int(os.environ.get("LLM_NUM_CTX", 16384))

    # Sampling temperature. Lower = more deterministic, higher = more creative.
    LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.2"))

    # Password required to access the app. Must be set in .env.
    APP_PASSWORD = os.environ.get("APP_PASSWORD")
    if not APP_PASSWORD:
        raise RuntimeError("APP_PASSWORD is not set. Add it to your .env file.")