from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import UniqueConstraint

from app.extensions import db
from app.models.base import uuid_pk

POSITION_NAMES = ("president", "governor", "senator", "woman_representative", "member_of_parliament", "mca")
# Real IEBC form-series prefix per position (verified — not the pilot's original
# assumption that Women Rep was "34A"; 34 is actually the Presidential series).
POSITION_LEVELS = ("national", "county", "constituency", "ward")


class ElectivePosition(db.Model):
    """Static reference data — the 6 elective seats in a Kenyan general
    election. Seeded once (see import_geography.py), never user-created.
    `level` is the geographic scope candidates for this position belong to
    (and what a campaign manager's agent assignment must resolve to for
    tallying) — e.g. Governor candidates are per-county, MP per-constituency."""

    __tablename__ = "elective_position"

    id = uuid_pk()
    name = db.Column(db.Text, nullable=False, unique=True)
    form_series = db.Column(db.Text, nullable=False)  # "34".."39"
    level = db.Column(db.Text, nullable=False)

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "form_series": self.form_series,
            "level": self.level,
        }


class Candidate(db.Model):
    """Discovered dynamically from Claude Vision extraction (see
    services/candidates.py's get_or_create_candidate) — not pre-seeded.
    Scoped by position + whichever geo FK matches position.level (all three
    null for a national position like President)."""

    __tablename__ = "candidate"
    __table_args__ = (
        UniqueConstraint(
            "position_id", "county_id", "constituency_id", "ward_id", "normalized_name",
            name="uq_candidate_scope_name",
        ),
    )

    id = uuid_pk()
    position_id = db.Column(UUID(as_uuid=True), db.ForeignKey("elective_position.id"), nullable=False)
    county_id = db.Column(UUID(as_uuid=True), db.ForeignKey("county.id"))
    constituency_id = db.Column(UUID(as_uuid=True), db.ForeignKey("constituency.id"))
    ward_id = db.Column(UUID(as_uuid=True), db.ForeignKey("ward.id"))
    full_name = db.Column(db.Text, nullable=False)
    normalized_name = db.Column(db.Text, nullable=False)  # uppercased/whitespace-collapsed, for get-or-create matching
    party = db.Column(db.Text)

    def to_dict(self):
        return {
            "id": str(self.id),
            "position_id": str(self.position_id),
            "county_id": str(self.county_id) if self.county_id else None,
            "constituency_id": str(self.constituency_id) if self.constituency_id else None,
            "ward_id": str(self.ward_id) if self.ward_id else None,
            "full_name": self.full_name,
            "party": self.party,
        }
