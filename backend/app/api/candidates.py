from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models import Candidate, ElectivePosition, VoteRecord
from app.services.candidates import get_or_create_candidate
from app.utils.errors import ApiError
from app.utils.rbac import role_required

bp = Blueprint("candidates", __name__, url_prefix="/api/candidates")

_SCOPE_KEY_FOR_LEVEL = {"county": "county_id", "constituency": "constituency_id", "ward": "ward_id"}


@bp.get("")
def list_candidates():
    """Candidates are matched dynamically as forms come in (see
    services/candidates.py), on top of whatever a campaign manager has
    pre-seeded via POST below — always scope by position, optionally by
    geography, or this returns every candidate ever recorded across every
    race."""
    q = Candidate.query
    position_id = request.args.get("position_id")
    if position_id:
        q = q.filter_by(position_id=position_id)
    for param, column in (
        ("county_id", Candidate.county_id),
        ("constituency_id", Candidate.constituency_id),
        ("ward_id", Candidate.ward_id),
    ):
        value = request.args.get(param)
        if value:
            q = q.filter(column == value)
    return jsonify([c.to_dict() for c in q.order_by(Candidate.full_name)])


@bp.post("")
@role_required("campaign_manager", "admin")
def create_candidate():
    """Lets a campaign manager pre-seed the official roster for a race, so
    later extractions match against a known name instead of only ever
    discovering candidates from whatever a form happens to say first."""
    data = request.get_json(force=True) or {}
    position_id = data.get("position_id")
    full_name = (data.get("full_name") or "").strip()
    if not position_id or not full_name:
        raise ApiError("position_id and full_name are required")

    position = db.session.get(ElectivePosition, position_id)
    if not position:
        raise ApiError("Unknown position", status_code=404)

    scope = {}
    scope_key = _SCOPE_KEY_FOR_LEVEL.get(position.level)
    if scope_key:
        if not data.get(scope_key):
            raise ApiError(f"{scope_key} is required for a {position.level}-level position")
        scope[scope_key] = data[scope_key]

    candidate = get_or_create_candidate(position, full_name, data.get("party"), **scope)
    db.session.commit()
    return jsonify(candidate.to_dict()), 201


@bp.delete("/<uuid:candidate_id>")
@role_required("campaign_manager", "admin")
def delete_candidate(candidate_id):
    candidate = db.session.get(Candidate, candidate_id)
    if not candidate:
        raise ApiError("Not found", status_code=404)
    if VoteRecord.query.filter_by(candidate_id=candidate.id).first():
        raise ApiError("Can't remove a candidate that already has votes recorded against them", status_code=409)
    db.session.delete(candidate)
    db.session.commit()
    return "", 204
