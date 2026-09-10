from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt

from app.extensions import db
from app.models import Agent, ElectivePosition, PollingStation, Ward, Constituency, County
from app.models.agent import PRIVILEGED_ROLES
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
    """Field agents by default — campaign managers assign stations/positions
    to agents, not to other coordinators/admins/viewers.

    `?role=` widens this so an admin can find the self-registered
    campaign-manager accounts waiting on activation. Restricted to admins:
    letting a campaign manager enumerate other campaign managers, coordinators
    and admins would hand them the phone numbers and emails of exactly the
    accounts worth targeting (every role signs in with a code to the address
    on file — see api/auth.py).
    """
    role = request.args.get("role", "agent")
    if role != "agent" and get_jwt().get("role") != "admin":
        raise ApiError("Only an admin can list accounts other than field agents", status_code=403)

    q = Agent.query.filter_by(role=role)
    if request.args.get("awaiting_activation") == "true":
        q = q.filter(Agent.activated_at.is_(None))
    return jsonify([_serialize(a) for a in q.order_by(Agent.full_name).all()])


@bp.patch("/<uuid:agent_id>/activation")
@role_required("admin")
def set_activation(agent_id):
    """Activates (or suspends) a privileged account — the gate that makes open
    campaign-manager signup safe. Until `activated_at` is set, api/auth.py
    issues that account a PENDING_ROLE token that satisfies no
    role_required(...) anywhere, so it can sign in and see its own status and
    nothing else.

    Admin-only on purpose: a campaign manager must not be able to activate
    other campaign managers, or the gate is self-service again.

    Suspending (`activated: false`) takes effect on the account's NEXT token —
    existing JWTs stay valid for up to JWT_ACCESS_TOKEN_EXPIRES because there
    is no revocation list yet (Phase 3.4). Rotate JWT_SECRET_KEY if you need a
    suspension to bite immediately.
    """
    agent = db.session.get(Agent, agent_id)
    if not agent:
        raise ApiError("Not found", status_code=404)
    if agent.role not in PRIVILEGED_ROLES:
        raise ApiError(f"{agent.role} accounts don't require activation", status_code=400)

    data = request.get_json(force=True, silent=True) or {}
    if "activated" not in data:
        raise ApiError("activated (true/false) is required")
    if not isinstance(data["activated"], bool):
        raise ApiError("activated must be true or false")

    agent.activated_at = datetime.now(timezone.utc) if data["activated"] else None
    db.session.commit()
    return jsonify(_serialize(agent))


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
