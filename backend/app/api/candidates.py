from flask import Blueprint, jsonify, request

from app.models import Candidate

bp = Blueprint("candidates", __name__, url_prefix="/api/candidates")


@bp.get("")
def list_candidates():
    """Candidates are discovered dynamically (see services/candidates.py) —
    always scope by position, optionally by geography, or this returns
    every candidate ever extracted across every race."""
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
