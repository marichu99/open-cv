"""Deduplication checks applied when a draft submission is finalized.

Exact byte-identical re-uploads are already blocked at the DB level by the
UNIQUE(station_id, form_type, image_sha256) constraint on form_submission.
This module handles the softer case: a second, genuinely different photo of
the same station+form already has an approved submission on file.
"""

from app.models import FormSubmission
from app.models.submission import TALLIED_STATUSES


def find_existing_approved(station_id, form_type, exclude_submission_id):
    return (
        FormSubmission.query.filter_by(station_id=station_id, form_type=form_type)
        .filter(FormSubmission.status.in_(TALLIED_STATUSES))
        .filter(FormSubmission.id != exclude_submission_id)
        .first()
    )
