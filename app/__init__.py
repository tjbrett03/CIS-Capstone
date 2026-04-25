from flask import Flask
from flask_session import Session
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import Config

# Instantiated at module level so routes.py can import and apply them as
# decorators before create_app() binds them to the Flask instance.
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Use server-side filesystem sessions instead of signed cookies,
    # so large message histories don't overflow the cookie size limit.
    Session(app)

    # Attach CSRF protection — validates tokens on all state-changing requests.
    csrf.init_app(app)

    # Attach rate limiter — individual limits are applied per route.
    limiter.init_app(app)

    from app.routes import main
    app.register_blueprint(main)

    # Load the Presidio/spaCy model into memory now so the first interview
    # completion doesn't pay a 2–3s cold-start hit.
    from app import pii
    pii.warmup()

    return app
