from sqlalchemy.dialects.postgresql import UUID

from app.extensions import db
from app.models.base import uuid_pk, utcnow

ROLES = ("agent", "campaign_manager", "coordinator", "admin", "viewer")

# An agent posted at one polling station is commonly responsible for
# multiple simultaneous races there (President + Woman Rep + MP, etc.), so
# this is many-to-many, not a single FK. Pure association table — no extra
# columns, no reason for it to be a full model.
agent_position = db.Table(
    "agent_position",
    db.Column("agent_id", UUID(as_uuid=True), db.ForeignKey("agent.id"), primary_key=True),
    db.Column("position_id", UUID(as_uuid=True), db.ForeignKey("elective_position.id"), primary_key=True),
)


class Agent(db.Model):
    """Doubles as the app's identity/user table — every role signs in via a
    one-time code emailed to `email` (see services/email.py, api/auth.py).
    Campaign managers additionally always get their code at the fixed inbox
    in api/auth.py's CAMPAIGN_MANAGER_OTP_EMAIL, on top of their own
    address. `assigned_station_id`/`positions` are set exclusively by a
    campaign_manager/admin (see api/agents.py) — never by the agent
    themselves, not even at signup."""

    __tablename__ = "agent"

    id = uuid_pk()
    full_name = db.Column(db.Text, nullable=False)
    phone_number = db.Column(db.Text, nullable=False, unique=True)
    email = db.Column(db.Text, unique=True)  # OTP delivery address
    phone_verified_at = db.Column(db.DateTime(timezone=True))
    assigned_station_id = db.Column(UUID(as_uuid=True), db.ForeignKey("polling_station.id"))
    role = db.Column(db.Text, nullable=False, default="agent")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    positions = db.relationship("ElectivePosition", secondary=agent_position, order_by="ElectivePosition.form_series")

    def to_dict(self):
        return {
            "id": str(self.id),
            "full_name": self.full_name,
            "phone_number": self.phone_number,
            "email": self.email,
            "phone_verified": self.phone_verified_at is not None,
            "role": self.role,
            "assigned_station_id": str(self.assigned_station_id) if self.assigned_station_id else None,
            "position_ids": [str(p.id) for p in self.positions],
        }


class OtpCode(db.Model):
    """Short-lived OTP for agent verification, dispatched over SMTP to
    `Agent.email` — see services/email.py and services/otp.py."""

    __tablename__ = "otp_code"

    id = uuid_pk()
    phone_number = db.Column(db.Text, nullable=False)
    code = db.Column(db.Text, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    consumed = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
