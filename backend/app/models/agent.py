from sqlalchemy.dialects.postgresql import UUID

from app.extensions import db
from app.models.base import uuid_pk, utcnow

ROLES = ("agent", "campaign_manager", "coordinator", "admin", "viewer", "aspirant")

#: Roles that can act on other people's data — assign agents to stations,
#: moderate submissions, manage candidates. Signup for these is open (see
#: api/auth.py's register_campaign_manager) but the role is inert until an
#: admin sets `activated_at`; until then the JWT carries PENDING_ROLE.
#: Plain "agent" is deliberately not here — an agent already can't do
#: anything until a campaign manager assigns them a position, so gating
#: them twice would just break field onboarding. `aspirant` is deliberately
#: NOT here either, on purpose (not an oversight) — the aspirant is the top
#: of this system's hierarchy, answering to no admin, so admin approval of
#: an aspirant account was removed; registering and verifying a phone number
#: is enough (see api/auth.py's register_aspirant). This does mean whoever
#: registers as aspirant first gets full unscoped read access immediately —
#: acceptable here because this deployment serves exactly one candidacy.
PRIVILEGED_ROLES = ("campaign_manager", "coordinator", "admin")

#: The role claim issued to a privileged account that hasn't been activated
#: yet. It matches no `role_required(...)` anywhere, so it grants nothing —
#: the account can sign in and see its own pending status, and nothing else.
PENDING_ROLE = "pending"

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
    themselves, not even at signup. `assigned_by` records which campaign
    manager last set that assignment, which is what scopes a campaign
    manager's read access to submissions/images/logs to their own agents
    (see app/api/submissions.py's can_view_submission). `candidate_id` is
    the aspirant-only counterpart: the race they declared at signup (see
    api/auth.py's register_aspirant), linked to their own Candidate roster
    entry so their vote count shows up in the tally like anyone else's.
    `aspirant_id` is the campaign-manager-only counterpart: which aspirant's
    campaign they signed up to run, chosen at registration from the list of
    already-registered aspirants (register_campaign_manager) — mirrors
    assigned_by one level up the hierarchy. Purely a declared relationship
    today, not a data-isolation boundary — every aspirant in this
    deployment shares the same candidates/positions/stations regardless of
    which campaign manager set them up (see the non-goal note on
    PRIVILEGED_ROLES: this is still a single-candidacy deployment)."""

    __tablename__ = "agent"

    id = uuid_pk()
    full_name = db.Column(db.Text, nullable=False)
    phone_number = db.Column(db.Text, nullable=False, unique=True)
    email = db.Column(db.Text, unique=True)  # OTP delivery address
    phone_verified_at = db.Column(db.DateTime(timezone=True))
    assigned_station_id = db.Column(UUID(as_uuid=True), db.ForeignKey("polling_station.id"))
    #: The campaign manager who last set this agent's assignment via
    #: PATCH /api/agents/:id/assignment. Null when an admin made the
    #: assignment instead, or when the agent has never been assigned.
    assigned_by = db.Column(UUID(as_uuid=True), db.ForeignKey("agent.id"))
    #: The aspirant's own candidacy — set once, at registration (see
    #: api/auth.py's register_aspirant). Null for every other role.
    candidate_id = db.Column(UUID(as_uuid=True), db.ForeignKey("candidate.id"))
    #: Campaign-manager-only: the aspirant (another Agent row, role=
    #: "aspirant") they registered under. Null for every other role.
    aspirant_id = db.Column(UUID(as_uuid=True), db.ForeignKey("agent.id"))
    role = db.Column(db.Text, nullable=False, default="agent")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    #: When an admin activated this account. NULL on a freshly self-registered
    #: privileged account, which is what makes it inert (see effective_role).
    #: Backfilled to now() for every pre-existing row by migration c3f1a72b9d84.
    activated_at = db.Column(db.DateTime(timezone=True))

    #: When this account explicitly consented to the privacy policy at
    #: registration (see api/auth.py's _record_consent) — the point of
    #: recording this at all is to have real, provable consent on file, not
    #: just a page nobody was ever asked to agree to. NULL for every account
    #: that registered before this existed; no backfill possible, for the
    #: same reason candidate_id/aspirant_id couldn't be — consent is a fact
    #: about what actually happened at signup, not something a migration can
    #: retroactively manufacture.
    privacy_consent_at = db.Column(db.DateTime(timezone=True))
    #: Which version of the privacy policy they agreed to (see
    #: PRIVACY_POLICY_VERSION in api/auth.py) — lets a future policy change
    #: identify exactly who consented under an older version and ought to be
    #: asked again, rather than silently treating stale consent as current.
    privacy_policy_version = db.Column(db.Text)

    positions = db.relationship("ElectivePosition", secondary=agent_position, order_by="ElectivePosition.form_series")
    candidate = db.relationship("Candidate")
    # foreign_keys is required here — Agent already has a second self-FK
    # (assigned_by), so SQLAlchemy can't infer which column this join
    # condition means without disambiguation.
    aspirant = db.relationship("Agent", remote_side=[id], foreign_keys=[aspirant_id])

    @property
    def awaiting_activation(self) -> bool:
        return self.role in PRIVILEGED_ROLES and self.activated_at is None

    @property
    def effective_role(self) -> str:
        """The role this account actually gets to act as — the single source
        of truth for what goes into the JWT claim. A privileged account that
        no admin has activated acts as PENDING_ROLE, which matches no
        role_required(...) anywhere, so RBAC needs no changes to honour it."""
        return PENDING_ROLE if self.awaiting_activation else self.role

    def to_dict(self):
        return {
            "id": str(self.id),
            "full_name": self.full_name,
            "phone_number": self.phone_number,
            "email": self.email,
            "phone_verified": self.phone_verified_at is not None,
            # The role the account *is*, for display; `effective_role` is what
            # it can currently *do*. They differ only while awaiting activation.
            "role": self.role,
            "effective_role": self.effective_role,
            "awaiting_activation": self.awaiting_activation,
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "assigned_station_id": str(self.assigned_station_id) if self.assigned_station_id else None,
            "assigned_by": str(self.assigned_by) if self.assigned_by else None,
            "position_ids": [str(p.id) for p in self.positions],
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "aspirant_id": str(self.aspirant_id) if self.aspirant_id else None,
            "aspirant_name": self.aspirant.full_name if self.aspirant else None,
            "privacy_consent_at": self.privacy_consent_at.isoformat() if self.privacy_consent_at else None,
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
