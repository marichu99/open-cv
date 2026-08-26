import logging

from flask import Flask, jsonify

from app.config import Config
from app.extensions import db, migrate, jwt, cors, socketio
from app.utils.errors import register_error_handlers


def create_app(config_object: type = Config) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object)

    # INFO-level logs (e.g. OTP codes in services/otp.py) reach `docker compose
    # logs backend` / gunicorn's stdout even when DEBUG is off.
    logging.basicConfig(level=logging.INFO)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})
    socketio.init_app(app, message_queue=None)

    from app import models  # noqa: F401  (registers models with SQLAlchemy)
    from app.api import BLUEPRINTS

    for bp in BLUEPRINTS:
        app.register_blueprint(bp)

    register_error_handlers(app)

    import seed
    import import_geography

    seed.register_cli(app)
    import_geography.register_cli(app)

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", service="tally333-backend")

    return app
