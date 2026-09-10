import os

#: Values that must never survive into production. These are committed to a
#: public repo, so a deployment still running one is signing JWTs with a
#: string anybody can read — i.e. anyone can forge {"role": "admin"}.
INSECURE_DEFAULTS = frozenset({
    "dev-secret-key",
    "dev-jwt-secret-key",
    "change-me-in-production",
})


class ConfigError(RuntimeError):
    """Raised at startup when production config is unsafe to serve with."""


def validate_production_config(app) -> None:
    """Fails closed before the app serves a single request.

    Only enforced when FLASK_ENV=production (the same switch services/email.py
    already uses), so local dev and the test suite keep their convenient
    defaults. Under Cloud Run this fails SAFE: a revision that raises on boot
    never passes its health check, so traffic stays on the previous revision
    instead of migrating to a misconfigured one.
    """
    if os.environ.get("FLASK_ENV", "development") != "production":
        return

    problems = []

    for key in ("SECRET_KEY", "JWT_SECRET_KEY"):
        if str(app.config.get(key)) in INSECURE_DEFAULTS:
            problems.append(f"{key} is still the placeholder value committed to the repo")

    # A dropped or typo'd CV_BACKEND previously fell back to the mock
    # extractor, which silently tallies deterministic FABRICATED results while
    # the dashboard looks entirely normal. That must never be a default.
    if app.config.get("CV_BACKEND") == "mock":
        problems.append("CV_BACKEND=mock would tally fabricated extraction data")

    if app.config.get("DEBUG"):
        # DEBUG returns the OTP in the API response body (api/auth.py), which
        # is a full account-takeover primitive for any account.
        problems.append("DEBUG is enabled, which exposes OTP codes in API responses")

    if problems:
        raise ConfigError(
            "Refusing to start in production with unsafe configuration:\n  - "
            + "\n  - ".join(problems)
        )


class Config:
    DEBUG = os.environ.get("DEBUG", "false").lower() in ("1", "true", "yes")
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-jwt-secret-key")
    JWT_ACCESS_TOKEN_EXPIRES = 60 * 60 * 12  # 12h — spans a polling day

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg2://tally333:tally333@localhost:5432/tally333",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    REDIS_URL = os.environ.get("REDIS_URL")  # None => single-process pub/sub

    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")

    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "instance/uploads")
    MAX_CONTENT_LENGTH = 15 * 1024 * 1024  # 15MB per upload

    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local")
    GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")

    CV_BACKEND = os.environ.get("CV_BACKEND", "mock")
    CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.85"))

    # Extraction queue — unset (default) means enqueue_extraction() runs
    # extraction synchronously inline instead of dispatching a Cloud Task.
    GCP_PROJECT = os.environ.get("GCP_PROJECT")
    CLOUD_TASKS_LOCATION = os.environ.get("CLOUD_TASKS_LOCATION")
    CLOUD_TASKS_QUEUE = os.environ.get("CLOUD_TASKS_QUEUE")
    EXTRACTION_WORKER_URL = os.environ.get("EXTRACTION_WORKER_URL")
    TASKS_INVOKER_SERVICE_ACCOUNT = os.environ.get("TASKS_INVOKER_SERVICE_ACCOUNT")


class TestConfig(Config):
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg2://tally333:tally333@localhost:5432/tally333_test",
    )
    UPLOAD_DIR = "instance/test_uploads"
