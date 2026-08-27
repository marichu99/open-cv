from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models import ElectivePosition
from app.services import tally_service
from app.utils.errors import ApiError

bp = Blueprint("tally", __name__, url_prefix="/api/tally")


def _load_position():
    position_id = request.args.get("position_id")
    if not position_id:
        raise ApiError("position_id is required")
    position = db.session.get(ElectivePosition, position_id)
    if not position:
        raise ApiError("Unknown position", status_code=404)
    return position


@bp.get("/positions")
def positions_with_data():
    """Positions that have at least one real submission so far, plus every
    position's scope list — drives the dashboard's position/scope selector."""
    position_ids = set(tally_service.positions_with_data())
    out = []
    for position in ElectivePosition.query.order_by(ElectivePosition.form_series):
        out.append({
            **position.to_dict(),
            "has_data": position.id in position_ids,
            "scopes": tally_service.sub_regions(position),
            "grouping_levels": tally_service.valid_groupings(position),
        })
    return jsonify(out)


@bp.get("/summary")
def summary():
    position = _load_position()
    scope_id = request.args.get("scope_id")
    if position.level != "national" and not scope_id:
        raise ApiError(f"scope_id is required for a {position.level}-level position")
    return jsonify(tally_service.candidate_totals(position, scope_id))


@bp.get("/progress")
def progress():
    position = _load_position()
    scope_id = request.args.get("scope_id")
    return jsonify(tally_service.stations_progress(position, scope_id))


@bp.get("/timeseries")
def timeseries():
    position = _load_position()
    scope_id = request.args.get("scope_id")
    granularity = request.args.get("granularity")
    return jsonify(tally_service.timeseries(position, scope_id, granularity))


@bp.get("/by_station")
def by_station():
    position = _load_position()
    scope_id = request.args.get("scope_id")
    if position.level != "national" and not scope_id:
        raise ApiError(f"scope_id is required for a {position.level}-level position")
    return jsonify(tally_service.votes_by_station(position, scope_id))


@bp.get("/by_group")
def by_group():
    position = _load_position()
    scope_id = request.args.get("scope_id")
    level = request.args.get("level", "station")
    if position.level != "national" and not scope_id:
        raise ApiError(f"scope_id is required for a {position.level}-level position")
    if level not in tally_service.valid_groupings(position):
        raise ApiError(f"'{level}' isn't a meaningful grouping for a {position.level}-level position")
    return jsonify(tally_service.votes_by_group(position, scope_id, level))
