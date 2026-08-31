import mimetypes
import os
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, current_app, send_file, Response
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.extensions import db, socketio
from app.models import Agent, PollingStation, FormSubmission, VoteRecord, VerificationLog
from app.models.submission import FORM_LEVEL_LETTERS, TALLIED_STATUSES
from app.services.storage import LocalStorage, GCSStorage
from app.services.dedup import find_existing_approved, supersede
from app.services.extraction_queue import enqueue_extraction
from app.services.pdf import is_pdf, pdf_first_page_to_image
from app.services.image_quality import looks_blank
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

    if looks_blank(image_path):
        try:
            os.remove(image_path)
        except OSError:
            pass
        raise ApiError(
            "This photo looks blank or unreadable — please retake it with the form clearly in frame.",
            status_code=422,
        )

    existing = FormSubmission.query.filter_by(
        station_id=station.id, form_type=form_type, image_sha256=sha256
    ).first()
    if existing:
        if existing.status not in ("draft", "processing"):
            raise ApiError("This exact image has already been uploaded for this station/form", status_code=409)
        # Neither a draft nor a still-processing submission is "uploaded"
        # until /finalize is called — this is an abandoned attempt from
        # earlier (e.g. the agent hit Retake, or a task is still in flight)
        # that was never confirmed. The DB's unique constraint on
        # (station_id, form_type, image_sha256) means the new upload can't
        # coexist with it, so replace it rather than block.
        db.session.delete(existing)
        db.session.flush()

    if current_app.config["STORAGE_BACKEND"] == "gcs":
        object_name = GCSStorage(current_app.config["GCS_BUCKET_NAME"]).upload(image_path, sha256)
        os.remove(image_path)
        image_path = object_name

    submission = FormSubmission(
        station_id=station.id,
        agent_id=get_jwt_identity(),
        position_id=position.id,
        form_type=form_type,
        image_path=image_path,
        image_sha256=sha256,
        captured_at=datetime.fromisoformat(captured_at_raw) if captured_at_raw else None,
        status="processing",
    )
    db.session.add(submission)
    db.session.commit()

    # Runs synchronously inline unless a Cloud Tasks queue is configured
    # (app/services/extraction_queue.py) — either way, submission.to_dict()
    # below correctly reflects whatever state it's in by the time this
    # returns: already-resolved "draft"/"extraction_failed" when run
    # inline, or still "processing" when genuinely dispatched to a queue.
    enqueue_extraction(str(submission.id))

    return jsonify(submission.to_dict()), 202


@bp.post("/<uuid:submission_id>/finalize")
@jwt_required()
def finalize(submission_id):
    submission = db.session.get(FormSubmission, submission_id)
    if not submission:
        raise ApiError("Not found", status_code=404)
    if str(submission.agent_id) != get_jwt_identity() and get_jwt().get("role") not in ("coordinator", "admin"):
        raise ApiError("Forbidden", status_code=403)
    if submission.status == "processing":
        raise ApiError("Still processing — try again shortly", status_code=409)
    if submission.status == "extraction_failed":
        message = (submission.warnings or ["Extraction failed for this photo — please retake it."])[0]
        raise ApiError(message, status_code=422)
    if submission.status != "draft":
        raise ApiError("Submission has already been finalized")

    # The submitting agent can fix a misread figure right here in the
    # preview — the same "corrected value wins" mechanism a coordinator uses
    # in the review dialog, just applied before the submission ever leaves
    # draft status.
    corrections = (request.get_json(silent=True) or {}).get("corrections") or []
    if corrections:
        by_candidate = {str(v.candidate_id): v for v in submission.vote_records}
        for correction in corrections:
            record = by_candidate.get(str(correction.get("candidate_id")))
            if not record:
                continue
            record.votes_corrected = correction.get("votes_corrected")
            record.manually_overridden = True
        db.session.add(
            VerificationLog(
                submission_id=submission.id,
                reviewer_id=get_jwt_identity(),
                action="manual_correct",
                notes="Corrected by the submitting agent before finalizing",
            )
        )

    threshold = current_app.config["CONFIDENCE_THRESHOLD"]
    duplicate = find_existing_approved(
        submission.station_id, submission.form_type, submission.stream_number, submission.id
    )

    # The agent has already seen the extracted figures and had the chance to
    # correct them (see the `corrections` handling above), so their
    # confirmation is authoritative — including over an earlier submission
    # for the same station, which this one supersedes rather than waiting on
    # a coordinator. Warnings — an arithmetic mismatch, low confidence,
    # anything Claude Vision itself flagged — still count toward the tally,
    # but stay visible for a coordinator to spot-check after the fact.
    warnings = list(submission.warnings or [])
    if not _arithmetic_ok(submission):
        warnings.append("Extracted candidate votes + rejected ballots don't add up to the declared total votes cast")
    if float(submission.ocr_confidence_avg or 0) / 100 < threshold:
        warnings.append(f"Overall extraction confidence below the {threshold:.0%} review threshold")
    submission.warnings = warnings

    submission.status = "auto_approved"
    submission.finalized_at = datetime.now(timezone.utc)
    if duplicate:
        submission.duplicate_of = duplicate.id
        supersede(duplicate, submission, submission.agent_id, "Superseded by a newer confirmed submission for this station")

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
    if current_app.config["STORAGE_BACKEND"] == "gcs":
        data = GCSStorage(current_app.config["GCS_BUCKET_NAME"]).download_bytes(submission.image_path)
        mimetype = mimetypes.guess_type(submission.image_path)[0] or "application/octet-stream"
        return Response(data, mimetype=mimetype)
    return send_file(submission.image_path)
