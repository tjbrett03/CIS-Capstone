from flask import Flask
from flask_session import Session
from flask_wtf.csrf import CSRFProtect
from config import Config

csrf = CSRFProtect()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Use server-side filesystem sessions instead of signed cookies,
    # so large message histories don't overflow the cookie size limit.
    Session(app)

    # Attach CSRF protection — validates tokens on all state-changing requests.
    csrf.init_app(app)

    from app.routes import main
    app.register_blueprint(main)

    return app
