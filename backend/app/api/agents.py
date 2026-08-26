from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models import Agent, ElectivePosition, PollingStation, Ward, Constituency, County
from app.utils.errors import ApiError
from app.utils.rbac import role_required

bp = Blueprint("agents", __name__, url_prefix="/api/agents")


def _serialize(agent: Agent):
    data = agent.to_dict()
    data["assigned_station_name"] = None
    data["ward_name"] = None
    data["constituency_name"] = None
    data["county_name"] = None
    if agent.assigned_station_id:
        station = db.session.get(PollingStation, agent.assigned_station_id)
        if station:
            ward = db.session.get(Ward, station.ward_id)
            constituency = db.session.get(Constituency, ward.constituency_id) if ward else None
            county = db.session.get(County, constituency.county_id) if constituency else None
            data["assigned_station_name"] = station.name
            data["ward_name"] = ward.name if ward else None
            data["constituency_name"] = constituency.name if constituency else None
            data["county_name"] = county.name if county else None
    data["position_names"] = [p.name for p in agent.positions]
    return data


@bp.get("")
@role_required("campaign_manager", "admin")
def list_agents():
    """Field agents only — campaign managers assign stations/positions to
    agents, not to other coordinators/admins/viewers."""
    agents = Agent.query.filter_by(role="agent").order_by(Agent.full_name).all()
    return jsonify([_serialize(a) for a in agents])


@bp.patch("/<uuid:agent_id>/assignment")
@role_required("campaign_manager", "admin")
def assign_station(agent_id):
    """The only place an agent's station/position assignment can be set —
    not self-service at signup (see api/auth.py's register_agent). An agent
    posted at one station commonly tracks several simultaneous races there,
    so `position_ids` replaces the agent's whole assigned set on each call —
    it's not an incremental add/remove."""
    agent = db.session.get(Agent, agent_id)
    if not agent or agent.role != "agent":
        raise ApiError("Not found", status_code=404)

    data = request.get_json(force=True) or {}

    if "assigned_station_id" in data:
        station_id = data.get("assigned_station_id") or None
        if station_id and not db.session.get(PollingStation, station_id):
            raise ApiError("Unknown polling station")
        agent.assigned_station_id = station_id

    if "position_ids" in data:
        position_ids = data.get("position_ids") or []
        positions = ElectivePosition.query.filter(ElectivePosition.id.in_(position_ids)).all()
        if len(positions) != len(set(position_ids)):
            raise ApiError("Unknown elective position")
        agent.positions = positions

    db.session.commit()
    return jsonify(_serialize(agent))
