import os


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

    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")

    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "instance/uploads")
    MAX_CONTENT_LENGTH = 15 * 1024 * 1024  # 15MB per upload

    CV_BACKEND = os.environ.get("CV_BACKEND", "mock")
    CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.85"))


class TestConfig(Config):
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg2://tally333:tally333@localhost:5432/tally333_test",
    )
    UPLOAD_DIR = "instance/test_uploads"
