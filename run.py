# Entry point for the Flask application.
# Load environment variables from .env before importing the app,
# so config values are available when create_app() runs.
from dotenv import load_dotenv

load_dotenv()

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run()
