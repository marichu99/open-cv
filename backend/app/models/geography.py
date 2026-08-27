from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import UniqueConstraint

from app.extensions import db
from app.models.base import uuid_pk


class County(db.Model):
    __tablename__ = "county"

    id = uuid_pk()
    name = db.Column(db.Text, nullable=False, unique=True)
    registered_voters = db.Column(db.Integer)

    constituencies = db.relationship("Constituency", backref="county", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "registered_voters": self.registered_voters,
        }


class Constituency(db.Model):
    __tablename__ = "constituency"

    id = uuid_pk()
    county_id = db.Column(UUID(as_uuid=True), db.ForeignKey("county.id"), nullable=False)
    name = db.Column(db.Text, nullable=False, unique=True)
    registered_voters = db.Column(db.Integer)

    wards = db.relationship("Ward", backref="constituency", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": str(self.id),
            "county_id": str(self.county_id),
            "name": self.name,
            "registered_voters": self.registered_voters,
        }


class Ward(db.Model):
    __tablename__ = "ward"
    __table_args__ = (UniqueConstraint("constituency_id", "name"),)

    id = uuid_pk()
    constituency_id = db.Column(UUID(as_uuid=True), db.ForeignKey("constituency.id"), nullable=False)
    name = db.Column(db.Text, nullable=False)

    stations = db.relationship("PollingStation", backref="ward", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": str(self.id),
            "constituency_id": str(self.constituency_id),
            "name": self.name,
        }


class PollingStation(db.Model):
    __tablename__ = "polling_station"

    id = uuid_pk()
    ward_id = db.Column(UUID(as_uuid=True), db.ForeignKey("ward.id"), nullable=False)
    # Nullable: the national bulk import (seed_data/kenya_geography.json) has no
    # official IEBC codes, only names. Real codes are backfilled for Nyamira only,
    # parsed from the sample Form 34A PDF filenames — see import_geography.py.
    iebc_code = db.Column(db.Text, unique=True)
    name = db.Column(db.Text, nullable=False)
    registered_voters = db.Column(db.Integer)
    stream_count = db.Column(db.SmallInteger, nullable=False, default=1)

    def to_dict(self):
        return {
            "id": str(self.id),
            "ward_id": str(self.ward_id),
            "iebc_code": self.iebc_code,
            "name": self.name,
            "registered_voters": self.registered_voters,
            "stream_count": self.stream_count,
        }
