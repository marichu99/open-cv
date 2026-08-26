from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, current_app, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.extensions import db, socketio
from app.models import Agent, PollingStation, FormSubmission, VoteRecord
from app.models.submission import FORM_LEVEL_LETTERS, TALLIED_STATUSES
from app.services.cv_pipeline import get_extraction_service
from app.services.storage import LocalStorage
from app.services.dedup import find_existing_approved
from app.services.pdf import is_pdf, pdf_first_page_to_image
from app.services.candidates import get_or_create_candidate, geo_scope_for_position
from app.utils.errors import ApiError
from app.utils.rbac import role_required

bp = Blueprint("submissions", __name__, url_prefix="/api/submissions")


def _arithmetic_ok(submission: FormSubmission) -> bool:
    if submission.total_votes_cast is None:
        return False
    total = sum(v.effective_votes for v in submission.vote_records) + (submission.rejected_ballots or 0)
    return total == submission.total_votes_cast


@bp.post("/draft")
@jwt_required()
def create_draft():
    if "image" not in request.files:
        raise ApiError("image file is required")

    agent = db.session.get(Agent, get_jwt_identity())
    if not agent or not agent.positions:
        raise ApiError("No elective position assigned yet — contact your campaign manager", status_code=403)

    position_id = request.form.get("position_id")
    if not position_id:
        raise ApiError("position_id is required")
    position = next((p for p in agent.positions if str(p.id) == position_id), None)
    if not position:
        raise ApiError("Not one of your assigned positions", status_code=403)

    station_id = request.form.get("station_id")
    form_level = request.form.get("form_level", "A")
    captured_at_raw = request.form.get("captured_at")

    if form_level not in FORM_LEVEL_LETTERS:
        raise ApiError(f"form_level must be one of {FORM_LEVEL_LETTERS}")
    form_type = f"{position.form_series}{form_level}"
    station = db.session.get(PollingStation, station_id)
    if not station:
        raise ApiError("Unknown polling station", status_code=404)

    upload = request.files["image"]
    if is_pdf(upload):
        try:
            upload = pdf_first_page_to_image(upload)
        except ValueError as exc:
            raise ApiError(f"Could not process PDF: {exc}")

    storage = LocalStorage(current_app.config["UPLOAD_DIR"])
    image_path, sha256 = storage.save(upload)

    existing = FormSubmission.query.filter_by(
        station_id=station.id, form_type=form_type, image_sha256=sha256
    ).first()
    if existing:
        raise ApiError("This exact image has already been uploaded for this station/form", status_code=409)

    service = get_extraction_service(current_app.config["CV_BACKEND"])
    result = service.extract(image_path, position, form_type)

    submission = FormSubmission(
        station_id=station.id,
        agent_id=get_jwt_identity(),
        position_id=position.id,
        form_type=form_type,
        image_path=image_path,
        image_sha256=sha256,
        captured_at=datetime.fromisoformat(captured_at_raw) if captured_at_raw else None,
        total_votes_cast=result.total_votes_cast,
        rejected_ballots=result.rejected_ballots,
        ocr_confidence_avg=round(result.overall_confidence * 100, 2),
        status="draft",
        warnings=result.warnings,
    )
    db.session.add(submission)
    db.session.flush()

    geo_scope = geo_scope_for_position(position, station)
    for field in result.votes:
        candidate = get_or_create_candidate(position, field.candidate_name, field.party, **geo_scope)
        db.session.add(
            VoteRecord(
                submission_id=submission.id,
                candidate_id=candidate.id,
                votes_detected=field.votes,
                field_confidence=round(field.confidence * 100, 2),
            )
        )
    db.session.commit()

    return jsonify(submission.to_dict()), 201


@bp.post("/<uuid:submission_id>/finalize")
@jwt_required()
def finalize(submission_id):
    submission = db.session.get(FormSubmission, submission_id)
    if not submission:
        raise ApiError("Not found", status_code=404)
    if str(submission.agent_id) != get_jwt_identity() and get_jwt().get("role") not in ("coordinator", "admin"):
        raise ApiError("Forbidden", status_code=403)
    if submission.status != "draft":
        raise ApiError("Submission has already been finalized")

    threshold = current_app.config["CONFIDENCE_THRESHOLD"]
    duplicate = find_existing_approved(submission.station_id, submission.form_type, submission.id)

    if duplicate:
        submission.status = "pending_review"
        submission.duplicate_of = duplicate.id
    elif submission.warnings or not _arithmetic_ok(submission):
        submission.status = "pending_review"
    elif float(submission.ocr_confidence_avg or 0) / 100 < threshold:
        submission.status = "pending_review"
    else:
        submission.status = "auto_approved"
        submission.finalized_at = datetime.now(timezone.utc)

    db.session.commit()

    if submission.status in TALLIED_STATUSES:
        socketio.emit("tally_updated", {"submission_id": str(submission.id)})

    return jsonify(submission.to_dict())


@bp.get("")
@role_required("coordinator", "admin")
def list_submissions():
    q = FormSubmission.query
    status = request.args.get("status")
    station_id = request.args.get("station_id")
    has_warnings = request.args.get("has_warnings")
    if status:
        q = q.filter(FormSubmission.status == status)
    if station_id:
        q = q.filter(FormSubmission.station_id == station_id)
    if has_warnings == "true":
        # Claude Vision flagged something ambiguous/inconsistent on the form
        # itself (see services/claude_vision.py) — distinct from other
        # pending-review reasons like a duplicate or a low confidence score.
        q = q.filter(db.func.json_array_length(FormSubmission.warnings) > 0)
    q = q.order_by(FormSubmission.uploaded_at.desc()).limit(200)
    return jsonify([s.to_dict(include_votes=False) for s in q])


@bp.get("/<uuid:submission_id>")
@jwt_required()
def get_submission(submission_id):
    submission = db.session.get(FormSubmission, submission_id)
    if not submission:
        raise ApiError("Not found", status_code=404)
    if str(submission.agent_id) != get_jwt_identity() and get_jwt().get("role") not in ("coordinator", "admin"):
        raise ApiError("Forbidden", status_code=403)
    return jsonify(submission.to_dict())


@bp.get("/<uuid:submission_id>/image")
@jwt_required()
def get_image(submission_id):
    submission = db.session.get(FormSubmission, submission_id)
    if not submission:
        raise ApiError("Not found", status_code=404)
    if str(submission.agent_id) != get_jwt_identity() and get_jwt().get("role") not in ("coordinator", "admin"):
        raise ApiError("Forbidden", status_code=403)
    return send_file(submission.image_path)
