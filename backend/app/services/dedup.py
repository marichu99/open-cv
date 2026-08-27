"""Deduplication checks applied when a draft submission is finalized.

Exact byte-identical re-uploads are already blocked at the DB level by the
UNIQUE(station_id, form_type, image_sha256) constraint on form_submission.
This module handles the softer case: a second, genuinely different photo of
the same station+form already has an approved submission on file.
"""

from app.extensions import db
from app.models import FormSubmission, VerificationLog
from app.models.submission import TALLIED_STATUSES


def find_existing_approved(station_id, form_type, exclude_submission_id):
    return (
        FormSubmission.query.filter_by(station_id=station_id, form_type=form_type)
        .filter(FormSubmission.status.in_(TALLIED_STATUSES))
        .filter(FormSubmission.id != exclude_submission_id)
        .first()
    )


def supersede(original: FormSubmission, replacement: FormSubmission, reviewer_id, notes: str) -> None:
    """Flips `original` to `duplicate` status — dropping it out of the
    tally — now that `replacement` is the submission that should count for
    this station+form. Used both when a fresh agent submission
    auto-supersedes an earlier one at finalize time, and when a coordinator
    manually approves a submission that had been flagged as a duplicate."""
    original.status = "duplicate"
    original.duplicate_of = replacement.id
    db.session.add(
        VerificationLog(submission_id=original.id, reviewer_id=reviewer_id, action="mark_duplicate", notes=notes)
    )
