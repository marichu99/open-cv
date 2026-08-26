from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import UniqueConstraint

from app.extensions import db
from app.models.base import uuid_pk, utcnow

#: Form letter suffix per aggregation level: A = polling station (what field
#: agents photograph), B/C/D = constituency/county/declaration collation
#: forms further up the chain. Prefixed with the position's form_series
#: (see ElectivePosition) to get the real IEBC form code, e.g. "39A".
FORM_LEVEL_LETTERS = ("A", "B", "C", "D")
STATUSES = ("draft", "auto_approved", "pending_review", "manually_approved", "rejected", "duplicate")
REVIEW_ACTIONS = ("auto_flag", "manual_correct", "approve", "reject", "mark_duplicate")

#: statuses whose votes count toward the live tally
TALLIED_STATUSES = ("auto_approved", "manually_approved")


class FormSubmission(db.Model):
    __tablename__ = "form_submission"
    __table_args__ = (UniqueConstraint("station_id", "form_type", "image_sha256"),)

    id = uuid_pk()
    station_id = db.Column(UUID(as_uuid=True), db.ForeignKey("polling_station.id"), nullable=False)
    agent_id = db.Column(UUID(as_uuid=True), db.ForeignKey("agent.id"), nullable=False)
    position_id = db.Column(UUID(as_uuid=True), db.ForeignKey("elective_position.id"), nullable=False)
    form_type = db.Column(db.Text, nullable=False)  # e.g. "39A" — position.form_series + FORM_LEVEL_LETTERS

    image_path = db.Column(db.Text, nullable=False)
    image_sha256 = db.Column(db.Text, nullable=False)

    captured_at = db.Column(db.DateTime(timezone=True))
    uploaded_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    finalized_at = db.Column(db.DateTime(timezone=True))

    total_votes_cast = db.Column(db.Integer)
    rejected_ballots = db.Column(db.Integer)
    ocr_confidence_avg = db.Column(db.Numeric(5, 2))

    status = db.Column(db.Text, nullable=False, default="draft")
    duplicate_of = db.Column(UUID(as_uuid=True), db.ForeignKey("form_submission.id"))

    #: cross-check / extraction warnings surfaced verbatim to the reviewer, e.g.
    #: "sum(candidate votes) + rejected != total cast"
    warnings = db.Column(db.JSON, default=list)

    station = db.relationship("PollingStation")
    agent = db.relationship("Agent")
    vote_records = db.relationship(
        "VoteRecord", backref="submission", cascade="all, delete-orphan", order_by="VoteRecord.candidate_id"
    )
    logs = db.relationship(
        "VerificationLog", backref="submission", cascade="all, delete-orphan",
        order_by="VerificationLog.created_at",
    )

    def to_dict(self, include_votes=True):
        data = {
            "id": str(self.id),
            "station_id": str(self.station_id),
            "station_name": self.station.name if self.station else None,
            "agent_id": str(self.agent_id),
            "agent_name": self.agent.full_name if self.agent else None,
            "position_id": str(self.position_id),
            "form_type": self.form_type,
            "image_url": f"/api/submissions/{self.id}/image",
            "captured_at": self.captured_at.isoformat() if self.captured_at else None,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
            "finalized_at": self.finalized_at.isoformat() if self.finalized_at else None,
            "total_votes_cast": self.total_votes_cast,
            "rejected_ballots": self.rejected_ballots,
            "ocr_confidence_avg": float(self.ocr_confidence_avg) if self.ocr_confidence_avg is not None else None,
            "status": self.status,
            "duplicate_of": str(self.duplicate_of) if self.duplicate_of else None,
            "warnings": self.warnings or [],
        }
        if include_votes:
            data["vote_records"] = [v.to_dict() for v in self.vote_records]
            data["logs"] = [l.to_dict() for l in self.logs]
        return data


class VoteRecord(db.Model):
    __tablename__ = "vote_record"
    __table_args__ = (UniqueConstraint("submission_id", "candidate_id"),)

    id = uuid_pk()
    submission_id = db.Column(UUID(as_uuid=True), db.ForeignKey("form_submission.id"), nullable=False)
    candidate_id = db.Column(UUID(as_uuid=True), db.ForeignKey("candidate.id"), nullable=False)
    votes_detected = db.Column(db.Integer, nullable=False)
    votes_corrected = db.Column(db.Integer)
    field_confidence = db.Column(db.Numeric(5, 2), nullable=False)
    manually_overridden = db.Column(db.Boolean, nullable=False, default=False)

    candidate = db.relationship("Candidate")

    @property
    def effective_votes(self):
        return self.votes_corrected if self.votes_corrected is not None else self.votes_detected

    def to_dict(self):
        return {
            "id": str(self.id),
            "candidate_id": str(self.candidate_id),
            "candidate_name": self.candidate.full_name if self.candidate else None,
            "votes_detected": self.votes_detected,
            "votes_corrected": self.votes_corrected,
            "effective_votes": self.effective_votes,
            "field_confidence": float(self.field_confidence),
            "manually_overridden": self.manually_overridden,
        }


class VerificationLog(db.Model):
    __tablename__ = "verification_log"

    id = uuid_pk()
    submission_id = db.Column(UUID(as_uuid=True), db.ForeignKey("form_submission.id"), nullable=False)
    reviewer_id = db.Column(UUID(as_uuid=True), db.ForeignKey("agent.id"))
    action = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    reviewer = db.relationship("Agent")

    def to_dict(self):
        return {
            "id": str(self.id),
            "reviewer_id": str(self.reviewer_id) if self.reviewer_id else None,
            "reviewer_name": self.reviewer.full_name if self.reviewer else None,
            "action": self.action,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
