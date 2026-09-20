from datetime import datetime, timezone

from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity

from app.extensions import db, socketio
from app.models import FormSubmission, VerificationLog
from app.models.submission import TALLIED_STATUSES
from app.services.dedup import supersede
from app.utils.errors import ApiError
from app.utils.rbac import role_required

bp = Blueprint("review", __name__, url_prefix="/api/submissions")

#: The only status change a coordinator/admin can make to a submission a
#: field agent has already finalized. Vote-figure corrections and outright
#: approve/reject are deliberately gone from this endpoint — the agent's own
#: resolution (see api/submissions.py's finalize) is final; a coordinator
#: cannot veto it. The one thing left is duplicate resolution: flagging that
#: two agents uploaded the same physical form isn't disputing either
#: agent's reading, it's preventing the same station's votes from being
#: counted twice.
_ACTION_TO_STATUS = {
    "mark_duplicate": "duplicate",
}


@bp.post("/<uuid:submission_id>/review")
@role_required("coordinator", "admin")
def review_submission(submission_id):
    """Duplicate resolution only — see _ACTION_TO_STATUS. `action` must be
    "mark_duplicate" (with `duplicate_of`), or "approve" to reverse an
    earlier mark_duplicate call on THIS submission (i.e. it turns out this
    one was the correct reading after all, so the submission it was marked
    a duplicate of gets superseded instead). Neither case touches vote
    figures or overrides a submission that was never flagged as a
    duplicate — that would be exactly the veto this endpoint no longer has."""
    submission = db.session.get(FormSubmission, submission_id)
    if not submission:
        raise ApiError("Not found", status_code=404)
    if submission.status in ("draft", "processing", "extraction_failed"):
        raise ApiError("Submission has not been finalized by the agent yet")

    data = request.get_json(force=True) or {}
    action = data.get("action")
    notes = data.get("notes")

    if action == "approve" and submission.duplicate_of:
        # Reversing an earlier mark_duplicate: this submission was flagged
        # as a duplicate of `original`, but that was wrong — restore this
        # one and demote the original instead, so exactly one of the two
        # counts.
        submission.status = "manually_approved"
        original = db.session.get(FormSubmission, submission.duplicate_of)
        if original and original.status in TALLIED_STATUSES:
            supersede(original, submission, get_jwt_identity(), f"Superseded by {submission.id} on manual review")
        db.session.add(
            VerificationLog(submission_id=submission.id, reviewer_id=get_jwt_identity(), action=action, notes=notes)
        )
    elif action in _ACTION_TO_STATUS:
        submission.status = _ACTION_TO_STATUS[action]
        if action == "mark_duplicate" and data.get("duplicate_of"):
            submission.duplicate_of = data["duplicate_of"]
        if submission.status in TALLIED_STATUSES and not submission.finalized_at:
            submission.finalized_at = datetime.now(timezone.utc)
        db.session.add(
            VerificationLog(submission_id=submission.id, reviewer_id=get_jwt_identity(), action=action, notes=notes)
        )
    elif action:
        raise ApiError(
            "A coordinator/admin can no longer correct vote figures or approve/reject a submission the field agent "
            "already finalized — that resolution is final. The only action available here is mark_duplicate (or "
            "approve, to reverse an earlier mark_duplicate on this same submission)."
        )

    db.session.commit()

    if submission.status in TALLIED_STATUSES:
        socketio.emit("tally_updated", {"submission_id": str(submission.id)})

    return jsonify(submission.to_dict())
