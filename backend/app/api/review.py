from datetime import datetime, timezone

from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity

from app.extensions import db, socketio
from app.models import FormSubmission, VoteRecord, VerificationLog
from app.models.submission import REVIEW_ACTIONS, TALLIED_STATUSES
from app.utils.errors import ApiError
from app.utils.rbac import role_required

bp = Blueprint("review", __name__, url_prefix="/api/submissions")

_ACTION_TO_STATUS = {
    "approve": "manually_approved",
    "reject": "rejected",
    "mark_duplicate": "duplicate",
}


@bp.post("/<uuid:submission_id>/review")
@role_required("coordinator", "admin")
def review_submission(submission_id):
    submission = db.session.get(FormSubmission, submission_id)
    if not submission:
        raise ApiError("Not found", status_code=404)
    if submission.status == "draft":
        raise ApiError("Submission has not been finalized by the agent yet")

    data = request.get_json(force=True) or {}
    action = data.get("action")
    corrections = data.get("corrections") or []
    notes = data.get("notes")

    if corrections:
        by_candidate = {str(v.candidate_id): v for v in submission.vote_records}
        for correction in corrections:
            record: VoteRecord = by_candidate.get(str(correction.get("candidate_id")))
            if not record:
                continue
            record.votes_corrected = correction.get("votes_corrected")
            record.manually_overridden = True
        db.session.add(
            VerificationLog(
                submission_id=submission.id,
                reviewer_id=get_jwt_identity(),
                action="manual_correct",
                notes=notes,
            )
        )

    if action:
        if action not in REVIEW_ACTIONS or action not in _ACTION_TO_STATUS:
            raise ApiError(f"action must be one of {list(_ACTION_TO_STATUS)}")
        submission.status = _ACTION_TO_STATUS[action]
        if action == "mark_duplicate" and data.get("duplicate_of"):
            submission.duplicate_of = data["duplicate_of"]
        if submission.status in TALLIED_STATUSES and not submission.finalized_at:
            submission.finalized_at = datetime.now(timezone.utc)
        db.session.add(
            VerificationLog(
                submission_id=submission.id,
                reviewer_id=get_jwt_identity(),
                action=action,
                notes=notes,
            )
        )

    db.session.commit()

    if submission.status in TALLIED_STATUSES:
        socketio.emit("tally_updated", {"submission_id": str(submission.id)})

    return jsonify(submission.to_dict())
