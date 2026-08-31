"""Endpoints called by Google Cloud infrastructure, not end users.

No JWT/app-level auth here — access control is Cloud Run IAM
(`--no-allow-unauthenticated` plus `roles/run.invoker` granted only to the
Cloud Tasks invoker service account; see docs/DEPLOYMENT.md's "Async form
extraction" section). Anything reaching this route has already been
authenticated at the platform level.
"""

from flask import Blueprint, request, jsonify

from app.services.extraction import process_extraction

bp = Blueprint("internal", __name__, url_prefix="/internal")


@bp.post("/submissions/extract")
def extract():
    submission_id = (request.get_json(force=True) or {}).get("submission_id")
    process_extraction(submission_id)
    return jsonify(status="ok")
