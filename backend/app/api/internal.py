"""Endpoints called by Google Cloud infrastructure, not end users.

Access control used to rest ENTIRELY on Cloud Run IAM
(`--no-allow-unauthenticated` on tally333-extraction-worker). That assumption
was false in practice: app/api/__init__.py registers this blueprint on every
service built from this image, and tally333-api is deployed
`--allow-unauthenticated` (docs/DEPLOYMENT.md). So a second, publicly
reachable copy of this route ran against the same database, letting anyone
POST a submission id to force a billed re-extraction and race the real worker.

So the OIDC token Cloud Tasks already attaches is now verified here, in the
application, instead of being assumed. Platform IAM stays as the outer layer;
this is the inner one.
"""

from flask import Blueprint, current_app, jsonify, request

from app.services.extraction import process_extraction
from app.utils.errors import ApiError

bp = Blueprint("internal", __name__, url_prefix="/internal")


def _verify_cloud_tasks_oidc() -> None:
    """Requires a Google-signed OIDC token issued to the Cloud Tasks invoker
    service account. Raises ApiError(404) on any failure — 404 rather than
    401/403 so this route is indistinguishable from "not here" to anyone
    without a valid token, matching how get_public_image avoids confirming
    that a non-public submission exists.

    If TASKS_INVOKER_SERVICE_ACCOUNT is unset, this deployment doesn't use
    Cloud Tasks at all (enqueue_extraction runs extraction inline — see
    services/extraction_queue.py), so nothing legitimate calls this route and
    it is refused outright. That keeps local dev and the test suite working
    without google-auth installed, while failing closed in production.
    """
    expected_sa = current_app.config.get("TASKS_INVOKER_SERVICE_ACCOUNT")
    if not expected_sa:
        raise ApiError("Not found", status_code=404)

    auth_header = request.headers.get("Authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ApiError("Not found", status_code=404)

    # Lazy import, matching GCSStorage/enqueue_extraction — google-auth
    # arrives transitively with google-cloud-tasks and is only needed on a
    # deployment that actually receives Cloud Tasks callbacks.
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    try:
        # audience=None: Cloud Tasks sets the audience to EXTRACTION_WORKER_URL,
        # but this app sits behind Cloud Run + an external LB with no ProxyFix,
        # so request.base_url can't be trusted to reconstruct that value for a
        # strict comparison. Signature, issuer and expiry are still verified;
        # the binding control is the service-account identity checked below,
        # which an attacker cannot forge without permission to impersonate it.
        claims = id_token.verify_oauth2_token(token, google_requests.Request(), audience=None)
    except Exception:
        current_app.logger.warning("internal: rejected a request with an invalid OIDC token")
        raise ApiError("Not found", status_code=404)

    if claims.get("email") != expected_sa or claims.get("email_verified") is not True:
        current_app.logger.warning(
            "internal: rejected OIDC token for unexpected principal %r", claims.get("email")
        )
        raise ApiError("Not found", status_code=404)


@bp.post("/submissions/extract")
def extract():
    _verify_cloud_tasks_oidc()
    submission_id = (request.get_json(force=True, silent=True) or {}).get("submission_id")
    if not submission_id:
        raise ApiError("submission_id is required")
    process_extraction(submission_id)
    return jsonify(status="ok")
