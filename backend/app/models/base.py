import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import UUID

from app.extensions import db


def uuid_pk():
    return db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def utcnow():
    return datetime.now(timezone.utc)
