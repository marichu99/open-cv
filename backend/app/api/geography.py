from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models import County, Constituency, Ward, PollingStation
from app.utils.errors import ApiError

bp = Blueprint("geography", __name__, url_prefix="/api/geography")

# No monolithic /tree endpoint here — at national scale (47 counties, 290
# constituencies, ~1,450 wards, ~24.6k polling stations) returning the whole
# hierarchy in one response doesn't scale. Cascading selects fetch each
# level lazily as the parent is chosen — see frontend/src/lib/hooks.ts.


@bp.get("/counties")
def list_counties():
    return jsonify([c.to_dict() for c in County.query.order_by(County.name)])


@bp.get("/constituencies")
def list_constituencies():
    county_id = request.args.get("county_id")
    q = Constituency.query
    if county_id:
        q = q.filter_by(county_id=county_id)
    return jsonify([c.to_dict() for c in q.order_by(Constituency.name)])


@bp.get("/wards")
def list_wards():
    constituency_id = request.args.get("constituency_id")
    q = Ward.query
    if constituency_id:
        q = q.filter_by(constituency_id=constituency_id)
    return jsonify([w.to_dict() for w in q.order_by(Ward.name)])


@bp.get("/stations")
def list_stations():
    ward_id = request.args.get("ward_id")
    q = PollingStation.query
    if ward_id:
        q = q.filter_by(ward_id=ward_id)
    return jsonify([s.to_dict() for s in q.order_by(PollingStation.name)])


@bp.get("/stations/<uuid:station_id>/ancestors")
def station_ancestors(station_id):
    """Resolves a station's full county/constituency/ward chain — used to
    prefill a cascading select from just a station id (e.g. an agent's
    campaign-manager-assigned station) without fetching the whole tree."""
    station = db.session.get(PollingStation, station_id)
    if not station:
        raise ApiError("Not found", status_code=404)
    ward = db.session.get(Ward, station.ward_id)
    constituency = db.session.get(Constituency, ward.constituency_id) if ward else None
    county = db.session.get(County, constituency.county_id) if constituency else None
    return jsonify({
        "station": station.to_dict(),
        "ward": ward.to_dict() if ward else None,
        "constituency": constituency.to_dict() if constituency else None,
        "county": county.to_dict() if county else None,
    })
