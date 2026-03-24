import os


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-key-change-me")
    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
