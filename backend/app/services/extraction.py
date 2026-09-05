"""Phase 2 of the upload pipeline — runs the CV extraction against an
already-persisted submission and fills in the result.

Called either synchronously inline (app/services/extraction_queue.py, when
no Cloud Tasks queue is configured) or from the internal endpoint Cloud
Tasks hits in production (app/api/internal.py). Both callers already have
an active Flask app context.
"""

import os
import tempfile

from flask import current_app

from app.extensions import db, socketio
from app.models import ElectivePosition, FormSubmission, VoteRecord
from app.services.candidates import get_or_create_candidate, geo_scope_for_position
from app.services.cv_pipeline import get_extraction_service
from app.services.location_check import location_mismatches
from app.services.position_check import position_mismatch
from app.services.storage import GCSStorage


def process_extraction(submission_id: str) -> None:
    submission = db.session.get(FormSubmission, submission_id)
    if not submission or submission.status != "processing":
        return  # already handled, deleted, or a stale/duplicate task delivery

    local_path, cleanup = _local_path_for(submission)
    try:
        _run_extraction(submission, local_path)
    finally:
        if cleanup:
            try:
                os.remove(local_path)
            except OSError:
                pass

    socketio.emit("submission_processed", {"submission_id": str(submission.id), "status": submission.status})


def _run_extraction(submission: FormSubmission, local_path: str) -> None:
    position = db.session.get(ElectivePosition, submission.position_id)
    service = get_extraction_service(current_app.config["CV_BACKEND"])
    result = service.extract(local_path, position, submission.form_type)

    # Checked before location: a wrong-race form is a worse mismatch than a
    # wrong-station one, and there's no point cross-checking the header
    # against this station if the results table isn't even for the position
    # the agent selected — get_or_create_candidate below trusts position_id
    # completely, so an undetected mismatch here would silently file real
    # candidates from one race under a different one.
    mismatch = position_mismatch(result.detected_position, position)
    if mismatch:
        submission.status = "extraction_failed"
        submission.warnings = [mismatch]
        db.session.commit()
        return

    mismatches = location_mismatches(result.detected_location, submission.station)
    if mismatches:
        submission.status = "extraction_failed"
        submission.warnings = [
            "This photo doesn't look like it's for the station you selected — "
            + "; ".join(mismatches)
            + ". Please retake it for the correct station."
        ]
        db.session.commit()
        return

    location = result.detected_location
    if location and location.stream_number is not None:
        submission.stream_number = location.stream_number
    if location and location.stream_count is not None and location.stream_count > (submission.station.stream_count or 1):
        submission.station.stream_count = location.stream_count

    submission.total_votes_cast = result.total_votes_cast
    submission.rejected_ballots = result.rejected_ballots
    submission.ocr_confidence_avg = round(result.overall_confidence * 100, 2)
    submission.warnings = result.warnings
    submission.status = "draft"

    geo_scope = geo_scope_for_position(position, submission.station)
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


def _local_path_for(submission: FormSubmission) -> tuple[str, bool]:
    """(local_path, should_cleanup). GCS-backed images are downloaded to a
    temp file for processing; local-backed ones are already at their
    permanent path — deleting that would delete the only copy."""
    if current_app.config["STORAGE_BACKEND"] == "gcs":
        data = GCSStorage(current_app.config["GCS_BUCKET_NAME"]).download_bytes(submission.image_path)
        ext = os.path.splitext(submission.image_path)[1] or ".jpg"
        fd, path = tempfile.mkstemp(suffix=ext)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        return path, True
    return submission.image_path, False
