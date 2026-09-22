from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity

from app.extensions import db
from app.models import Agent, ElectivePosition, PollingStation, Ward, Constituency, County, FormSubmission
from app.models.agent import PRIVILEGED_ROLES
from app.models.submission import TALLIED_STATUSES
from app.services.candidates import inherited_assignment
from app.utils.errors import ApiError
from app.utils.rbac import role_required

bp = Blueprint("agents", __name__, url_prefix="/api/agents")


def _serialize(agent: Agent, with_coverage: bool = False):
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
    # Field-agent only: what their campaign-manager -> aspirant chain
    # already implies about their race/geography, before this campaign
    # manager has assigned anything explicitly — see
    # services/candidates.py's inherited_assignment. Lets the assignment
    # dialog default (and the backend below enforce) to the aspirant's own
    # race instead of a blank slate across all 47 counties.
    data["inherited_assignment"] = inherited_assignment(agent) if agent.role == "agent" else None
    if with_coverage:
        latest = (
            FormSubmission.query.filter_by(agent_id=agent.id)
            .order_by(FormSubmission.uploaded_at.desc())
            .first()
        )
        data["latest_submission_status"] = latest.status if latest else None
        data["latest_submission_at"] = latest.uploaded_at.isoformat() if latest and latest.uploaded_at else None
        data["has_tallied_submission"] = latest.status in TALLIED_STATUSES if latest else False
    return data


@bp.get("")
@role_required("campaign_manager", "admin", "aspirant")
def list_agents():
    """Field agents by default — campaign managers assign stations/positions
    to agents, not to other coordinators/admins/viewers.

    `?role=` widens this. Admin can list any role — the one account with
    cross-cutting oversight. An aspirant may additionally list
    `role=campaign_manager` (scoped to their own, see below) so they can see
    and approve the campaign managers who registered under them — see
    `PATCH /:id/activation`. Nobody else can list a role other than `agent`:
    letting a plain campaign manager enumerate other campaign
    managers/coordinators/admins would hand them the phone numbers and
    emails of exactly the accounts worth targeting (every role signs in
    with a code to the address on file — see api/auth.py).

    `?with_coverage=true` adds each field agent's latest submission
    status/timestamp, so an aspirant or campaign manager can see who has
    uploaded a form and who hasn't — no separate endpoint for that.

    Field-agent results (the default `role=agent`) are scoped by who's
    calling — a campaign manager sees only agents who picked them at signup
    (Agent.assigned_by, see api/auth.py's register_agent); an aspirant sees
    only agents whose campaign manager picked THAT aspirant in turn
    (Agent.assigned_by -> Agent.aspirant_id), a two-hop cascade down the
    same hierarchy campaign-manager signup declares. An aspirant listing
    `role=campaign_manager` is scoped the same way one hop up
    (Agent.aspirant_id == caller) — they can never see another aspirant's
    campaign managers. Admin stays unscoped in every case.
    """
    role = request.args.get("role", "agent")
    caller_role = get_jwt().get("role")
    caller_identity = get_jwt_identity()
    if caller_role == "admin":
        pass  # unscoped, any role
    elif caller_role == "aspirant":
        if role not in ("agent", "campaign_manager"):
            raise ApiError("Aspirants can only list field agents or their own campaign managers", status_code=403)
    elif role != "agent":
        raise ApiError("Only an admin can list accounts other than field agents", status_code=403)

    q = Agent.query.filter_by(role=role)
    if role == "agent" and caller_role == "campaign_manager":
        q = q.filter(Agent.assigned_by == caller_identity)
    elif role == "agent" and caller_role == "aspirant":
        their_cms = db.session.query(Agent.id).filter(Agent.role == "campaign_manager", Agent.aspirant_id == caller_identity)
        q = q.filter(Agent.assigned_by.in_(their_cms))
    elif role == "campaign_manager" and caller_role == "aspirant":
        q = q.filter(Agent.aspirant_id == caller_identity)
    if request.args.get("awaiting_activation") == "true":
        q = q.filter(Agent.activated_at.is_(None))
    with_coverage = request.args.get("with_coverage") == "true"
    return jsonify([_serialize(a, with_coverage=with_coverage) for a in q.order_by(Agent.full_name).all()])


@bp.patch("/<uuid:agent_id>/activation")
@role_required("admin", "aspirant")
def set_activation(agent_id):
    """Activates (or suspends) a privileged account — the gate that makes open
    campaign-manager signup safe. Until `activated_at` is set, api/auth.py
    issues that account a PENDING_ROLE token that satisfies no
    role_required(...) anywhere, so it can sign in and see its own status and
    nothing else.

    Admin can activate anyone in PRIVILEGED_ROLES — cross-cutting oversight,
    same as everywhere else in this file. An aspirant can *only* activate a
    campaign_manager who registered under THEM specifically
    (agent.aspirant_id == caller) — never another aspirant's campaign
    manager, and never a coordinator/admin account (those still need an
    actual admin). This is the intended primary path now: the aspirant
    knows who their real campaign managers are far better than a central
    admin does, so they're the ones expected to actually use this day to
    day — admin keeps the capability too, as a backstop, not because
    aspirant approval is provisional.

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

    if get_jwt().get("role") == "aspirant":
        if agent.role != "campaign_manager" or str(agent.aspirant_id) != get_jwt_identity():
            raise ApiError(
                "You can only approve campaign managers who registered under your own campaign",
                status_code=403,
            )

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
    not self-service at signup (see api/auth.py's register_agent, which
    only auto-declares the race, never a station). An agent posted at one
    station commonly tracks several simultaneous races there, so
    `position_ids` replaces the agent's whole assigned set on each call —
    it's not an incremental add/remove.

    `assigned_station_id` is cross-checked against whatever geography this
    agent's campaign-manager -> aspirant chain already implies (see
    services/candidates.py's inherited_assignment) — a station outside that
    scope is rejected with 400 rather than silently accepted."""
    agent = db.session.get(Agent, agent_id)
    if not agent or agent.role != "agent":
        raise ApiError("Not found", status_code=404)
    # An agent now picks their campaign manager at signup (see
    # api/auth.py's register_agent), so assigned_by is set from day one —
    # a different campaign manager calling this is exactly the cross-CM
    # visibility this whole hierarchy exists to prevent, not just a listing
    # gap. Legacy agents that predate this feature (assigned_by still null)
    # can still be claimed by whichever CM assigns them first.
    if get_jwt().get("role") == "campaign_manager" and agent.assigned_by and str(agent.assigned_by) != get_jwt_identity():
        raise ApiError("This agent is linked to a different campaign manager", status_code=403)

    data = request.get_json(force=True) or {}

    if "assigned_station_id" in data:
        station_id = data.get("assigned_station_id") or None
        station = db.session.get(PollingStation, station_id) if station_id else None
        if station_id and not station:
            raise ApiError("Unknown polling station")

        # Cross-check the station actually falls within the geography this
        # agent's campaign-manager -> aspirant chain already implies (see
        # services/candidates.py's inherited_assignment) — the same
        # "trust nothing declared, verify against what's actually linked"
        # posture the extraction pipeline uses for a submission's own
        # declared station (services/location_check.py). Without this, a
        # campaign manager could assign an agent tracking a Wajir Senate
        # race to a Mombasa polling station with nothing catching it before
        # the vote lands in the wrong scope entirely. Only one of
        # county/constituency/ward is ever non-null on a given inherited
        # scope (it matches the aspirant's own position level), so at most
        # one of these three checks actually fires.
        if station:
            inherited = inherited_assignment(agent)
            if inherited:
                ward = db.session.get(Ward, station.ward_id)
                constituency = db.session.get(Constituency, ward.constituency_id) if ward else None
                county_id = constituency.county_id if constituency else None

                if inherited["ward"] and inherited["ward"]["id"] != str(station.ward_id):
                    raise ApiError(
                        f"This station isn't in {inherited['ward']['name']} ward — that's where this "
                        f"agent's race ({inherited['aspirant_name']}'s campaign) is actually running.",
                        status_code=400,
                    )
                if inherited["constituency"] and (not constituency or inherited["constituency"]["id"] != str(constituency.id)):
                    raise ApiError(
                        f"This station isn't in {inherited['constituency']['name']} constituency — that's where "
                        f"this agent's race ({inherited['aspirant_name']}'s campaign) is actually running.",
                        status_code=400,
                    )
                if inherited["county"] and (not county_id or inherited["county"]["id"] != str(county_id)):
                    raise ApiError(
                        f"This station isn't in {inherited['county']['name']} county — that's where this "
                        f"agent's race ({inherited['aspirant_name']}'s campaign) is actually running.",
                        status_code=400,
                    )

        agent.assigned_station_id = station_id

    if "position_ids" in data:
        position_ids = data.get("position_ids") or []
        positions = ElectivePosition.query.filter(ElectivePosition.id.in_(position_ids)).all()
        if len(positions) != len(set(position_ids)):
            raise ApiError("Unknown elective position")
        agent.positions = positions

    # Records which campaign manager owns this assignment — this is what
    # scopes their later read access to the agent's submissions/images/logs
    # (see app/api/submissions.py's can_view_submission). An admin making
    # the assignment isn't "a managing CM" for that purpose, so leave
    # assigned_by untouched in that case rather than overwrite it with the
    # admin's own id.
    if get_jwt().get("role") == "campaign_manager":
        agent.assigned_by = get_jwt_identity()

    db.session.commit()
    return jsonify(_serialize(agent))
