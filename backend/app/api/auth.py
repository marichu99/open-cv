from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt

from app.extensions import db
from app.models import Agent, ElectivePosition
from app.services.candidates import get_or_create_candidate, inherited_assignment
from app.services.otp import generate_and_send_otp, verify_otp
from app.utils.errors import ApiError
from app.utils.phone import normalize_phone_number

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

#: Bumped whenever the privacy policy materially changes. Recorded on every
#: account alongside privacy_consent_at (see _record_consent below) so a
#: stale consent — someone who agreed to an older version — can be told
#: apart from a current one, rather than treating every past "yes" as
#: valid forever. Keep in sync with frontend/src/pages/PrivacyPolicyPage.tsx.
PRIVACY_POLICY_VERSION = "2026-09-23"


def _require_consent(data: dict) -> None:
    """Every self-registration route below calls this alongside its other
    required-field checks — a silent default here would be exactly the
    "privacy policy nobody was ever actually asked to agree to" gap this
    exists to close."""
    if data.get("consent") is not True:
        raise ApiError("You must agree to the privacy policy to sign up", status_code=400)


def _record_consent(agent: "Agent") -> None:
    """Stamps consent onto the account — called once _require_consent has
    already passed. Idempotent on re-registration (an unverified row
    signing up again before verifying): re-stamps the timestamp/version
    rather than leaving the first attempt's consent as the one on
    permanent record."""
    agent.privacy_consent_at = datetime.now(timezone.utc)
    agent.privacy_policy_version = PRIVACY_POLICY_VERSION

# Same mapping as api/candidates.py's create_candidate — kept in sync there,
# not imported, since that one is blueprint-private and this is the only
# other place a position's required geography scope needs resolving.
_SCOPE_KEY_FOR_LEVEL = {"county": "county_id", "constituency": "constituency_id", "ward": "ward_id"}

# Privileged-signup codes (campaign manager, aspirant) are copied to this
# inbox as a MONITORING channel: it means a rogue signup or sign-in can't go
# unnoticed by the team. The name is historical — it now covers every role
# that self-registers into PRIVILEGED_ROLES, not just campaign managers.
#
# It is explicitly NOT a second factor, and earlier comments here claimed it
# was. verify_agent() below needs only (phone_number, code) and never proves
# control of any mailbox — so copying one code to two addresses is an OR, not
# an AND: whoever holds EITHER inbox can complete a sign-in. Privilege is
# gated by admin activation (see Agent.effective_role), not by this address.
#
# TODO: this is an unrotatable personal address hardcoded in source; moving it
# to a config value / team alias is tracked as Phase 3 work.
CAMPAIGN_MANAGER_OTP_EMAIL = "marichufx@gmail.com"

#: Roles whose sign-in/sign-up codes are always mirrored to the monitoring
#: inbox above, on top of the account's own address.
_MONITORED_ROLES = ("campaign_manager", "aspirant")


def _issue_token(agent: Agent):
    # effective_role, never agent.role — a self-registered privileged account
    # that no admin has activated must carry the inert PENDING_ROLE claim.
    # rbac.role_required() reads this claim, so the gate needs nothing else.
    claims = {"role": agent.effective_role, "full_name": agent.full_name}
    token = create_access_token(identity=str(agent.id), additional_claims=claims)
    return {"access_token": token, "agent": agent.to_dict()}


def _otp_email_for(agent: Agent) -> str | list[str]:
    """Every role signs in with a one-time code, emailed to the address on
    file — monitored roles (see _MONITORED_ROLES) additionally always get it
    at the fixed inbox above, so it's never solely in one person's control."""
    if not agent.email:
        raise ApiError(
            "No email on file for this account — ask an admin to add one before you can sign in",
            status_code=400,
        )
    if agent.role in _MONITORED_ROLES:
        return [agent.email, CAMPAIGN_MANAGER_OTP_EMAIL]
    return agent.email


def _validate_and_check_email(email: str | None, phone_number: str) -> None:
    if email and "@" not in email:
        raise ApiError("email is not valid")
    if email and Agent.query.filter(Agent.email == email, Agent.phone_number != phone_number).first():
        raise ApiError("Email is already in use")


@bp.post("/agents/register")
def register_agent():
    """Agent signup. Re-registering an already phone-verified number is
    rejected so a new account can't be silently reclaimed — sign in via
    /agents/otp/request instead. Station/position assignment is deliberately
    not accepted here — agents don't pick their own ward/station; a
    coordinator/admin assigns that afterwards via PATCH
    /api/agents/:id/assignment (see api/agents.py).

    campaign_manager_id IS accepted (required) — the agent still picks who
    they report to, same as a campaign manager picks their aspirant at
    register_campaign_manager. This is what Agent.assigned_by scopes on:
    a campaign manager's own agent roster (GET /api/agents), and an
    aspirant's, are both filtered by this chain (see api/agents.py's
    list_agents and api/submissions.py's can_view_submission) — without it,
    every campaign manager would see every agent in the country.

    That same chain already implies which race this agent is tracking —
    whichever position their campaign manager's own aspirant is running
    for — so it's auto-declared here rather than left for the campaign
    manager to re-pick from scratch (see services/candidates.py's
    inherited_assignment, also used by api/agents.py to show/enforce the
    geography half of the same inheritance). Additive only, never
    replacing: if this agent already carries other positions (e.g. a
    campaign manager assigned some while this row sat unverified), those
    are kept, not overwritten — this only adds the inherited one if it's
    missing. The agent still can't upload anything until a campaign
    manager sets an actual polling station (see api/agents.py's
    assign_station) — this just saves them re-declaring the obvious race."""
    data = request.get_json(force=True) or {}
    full_name = (data.get("full_name") or "").strip()
    phone_number = normalize_phone_number(data.get("phone_number") or "")
    email = (data.get("email") or "").strip().lower() or None
    campaign_manager_id = data.get("campaign_manager_id")
    if not full_name or not phone_number or not campaign_manager_id:
        raise ApiError("full_name, phone_number, and campaign_manager_id are required")
    _require_consent(data)
    _validate_and_check_email(email, phone_number)

    campaign_manager = db.session.get(Agent, campaign_manager_id)
    if not campaign_manager or campaign_manager.role != "campaign_manager":
        raise ApiError("Unknown campaign manager", status_code=404)

    agent = Agent.query.filter_by(phone_number=phone_number).first()
    # A phone number commits to one role at signup — even before verification,
    # so an abandoned agent signup can't be silently reclaimed as a campaign
    # manager (or vice versa) by registering again with the same number.
    if agent and agent.role != "agent":
        raise ApiError("This phone number is already registered under a different role — sign in instead", status_code=409)
    if agent and agent.phone_verified_at is not None:
        raise ApiError("Phone number already registered — sign in instead", status_code=409)

    if not agent:
        agent = Agent(full_name=full_name, phone_number=phone_number, role="agent")
        db.session.add(agent)
    else:
        agent.full_name = full_name

    if email:
        agent.email = email
    agent.assigned_by = campaign_manager.id
    _record_consent(agent)

    inherited = inherited_assignment(agent)
    if inherited and inherited["position"]:
        position = db.session.get(ElectivePosition, inherited["position"]["id"])
        if position and position not in agent.positions:
            agent.positions.append(position)

    db.session.commit()

    code = generate_and_send_otp(phone_number, email=agent.email)
    response = {"message": "OTP sent", "phone_number": phone_number}
    if current_app.debug:
        response["debug_otp"] = code  # never exposed outside debug mode
    return jsonify(response), 201


@bp.get("/aspirants")
def list_aspirants():
    """Unauthenticated on purpose — a prospective campaign manager needs this
    to pick which aspirant they're signing up under, before they have any
    account at all. Deliberately minimal: id/name plus the race and party
    (read off the linked Candidate — see register_aspirant) so the picker
    can disambiguate two aspirants with similar names; no phone/email, which
    the full Agent record carries but has no business being public."""
    aspirants = Agent.query.filter_by(role="aspirant").order_by(Agent.full_name).all()
    out = []
    for a in aspirants:
        position = db.session.get(ElectivePosition, a.candidate.position_id) if a.candidate else None
        out.append({
            "id": str(a.id),
            "full_name": a.full_name,
            "position_name": position.name if position else None,
            "party": a.candidate.party if a.candidate else None,
        })
    return jsonify(out)


@bp.get("/campaign_managers")
def list_campaign_managers_public():
    """Unauthenticated, deliberately minimal (id + name only) — same
    rationale as list_aspirants above. Used two ways by the frontend
    SignupPage: bare, to gate field-agent signup on "does a campaign
    manager exist yet"; with ?aspirant_id=, to populate the second half of
    an agent's aspirant -> campaign manager cascade (an agent can only pick
    a campaign manager who registered under the same aspirant they picked).
    Not to be confused with GET /api/agents?role=campaign_manager, which is
    admin-only and returns full PII."""
    q = Agent.query.filter_by(role="campaign_manager")
    aspirant_id = request.args.get("aspirant_id")
    if aspirant_id:
        q = q.filter_by(aspirant_id=aspirant_id)
    managers = q.order_by(Agent.full_name).all()
    return jsonify([{"id": str(m.id), "full_name": m.full_name} for m in managers])


@bp.post("/campaign_managers/register")
def register_campaign_manager():
    """Campaign manager signup — open to anyone, but the role is INERT until
    an admin activates it (PATCH /api/agents/:id/activation).

    Signing up and verifying yields a token carrying PENDING_ROLE, which
    matches no role_required(...) anywhere, so a self-registered account can
    see its own pending status and nothing else. Before the activation gate,
    this endpoint handed any anonymous caller the ability to reassign every
    agent in the country and dump every agent's PII via GET /api/agents.

    Also links the account to the aspirant they're campaigning for —
    aspirant_id is required and must name an existing aspirant account (see
    GET /aspirants above), mirroring how an agent later gets tied to the
    campaign manager who assigns them (see Agent.assigned_by). If no
    aspirant has registered yet, campaign manager signup is blocked rather
    than left dangling — the aspirant is the top of this hierarchy and is
    meant to sign up first.

    The OTP is also copied to CAMPAIGN_MANAGER_OTP_EMAIL so the team sees
    signups as they happen — a monitoring channel, not a second factor; see
    the note on that constant."""
    data = request.get_json(force=True) or {}
    full_name = (data.get("full_name") or "").strip()
    phone_number = normalize_phone_number(data.get("phone_number") or "")
    email = (data.get("email") or "").strip().lower() or None
    aspirant_id = data.get("aspirant_id")
    if not full_name or not phone_number or not email or not aspirant_id:
        raise ApiError("full_name, phone_number, email, and aspirant_id are required")
    _require_consent(data)
    _validate_and_check_email(email, phone_number)

    aspirant = db.session.get(Agent, aspirant_id)
    if not aspirant or aspirant.role != "aspirant":
        raise ApiError("Unknown aspirant", status_code=404)

    agent = Agent.query.filter_by(phone_number=phone_number).first()
    # Same guard as agent signup, mirrored: a phone number that already
    # started (even unverified) as a field agent can't be reclaimed as a
    # campaign manager with the same number — the two roles are mutually
    # exclusive per account, not just per verified account.
    if agent and agent.role != "campaign_manager":
        raise ApiError("This phone number is already registered under a different role — sign in instead", status_code=409)
    if agent and agent.phone_verified_at is not None:
        raise ApiError("Phone number already registered — sign in instead", status_code=409)

    if not agent:
        agent = Agent(full_name=full_name, phone_number=phone_number, role="campaign_manager")
        db.session.add(agent)
    else:
        agent.full_name = full_name

    agent.email = email
    agent.aspirant_id = aspirant.id
    _record_consent(agent)
    db.session.commit()

    code = generate_and_send_otp(phone_number, email=[email, CAMPAIGN_MANAGER_OTP_EMAIL])
    response = {
        "message": (
            f"OTP sent to {email} and {CAMPAIGN_MANAGER_OTP_EMAIL}. "
            "Your account needs an admin to activate it before you can manage agents."
        ),
        "phone_number": phone_number,
        "awaiting_activation": agent.awaiting_activation,
    }
    if current_app.debug:
        response["debug_otp"] = code  # never exposed outside debug mode
    return jsonify(response), 201


@bp.post("/aspirants/register")
def register_aspirant():
    """Aspirant (candidate) signup — unlike register_campaign_manager below,
    NOT gated by admin activation: "aspirant" isn't in PRIVILEGED_ROLES (see
    that tuple's comment), by design — the aspirant is the top of this
    system's hierarchy, so no admin approves them. Verifying the OTP is
    enough for the account to immediately read every submission/image/log
    system-wide (see can_view_submission), which is why the signup is still
    monitored (copied to CAMPAIGN_MANAGER_OTP_EMAIL below) even without a
    gate — the team sees it happen, they just can't block it.

    Also declares the race itself: position_id is required, plus whatever
    geography scope that position's level needs (same rule as POST
    /api/candidates — see _SCOPE_KEY_FOR_LEVEL). That's resolved via
    get_or_create_candidate, the same lookup a form extraction or a
    campaign-manager-seeded roster entry uses, so the aspirant's account
    lands on their real Candidate row (matching one a campaign manager
    already added by hand) instead of always creating a duplicate.

    The OTP is also copied to CAMPAIGN_MANAGER_OTP_EMAIL so the team sees the
    signup as it happens — a monitoring channel, not a second factor; see the
    note on that constant."""
    data = request.get_json(force=True) or {}
    full_name = (data.get("full_name") or "").strip()
    phone_number = normalize_phone_number(data.get("phone_number") or "")
    email = (data.get("email") or "").strip().lower() or None
    position_id = data.get("position_id")
    party = (data.get("party") or "").strip() or None
    if not full_name or not phone_number or not email or not position_id:
        raise ApiError("full_name, phone_number, email, and position_id are required")
    _require_consent(data)
    _validate_and_check_email(email, phone_number)

    position = db.session.get(ElectivePosition, position_id)
    if not position:
        raise ApiError("Unknown position", status_code=404)

    scope = {}
    scope_key = _SCOPE_KEY_FOR_LEVEL.get(position.level)
    if scope_key:
        if not data.get(scope_key):
            raise ApiError(f"{scope_key} is required for a {position.level}-level position")
        scope[scope_key] = data[scope_key]

    agent = Agent.query.filter_by(phone_number=phone_number).first()
    # Same guard as agent/campaign-manager signup: a phone number that
    # already started as some other role can't be reclaimed as an aspirant
    # with the same number.
    if agent and agent.role != "aspirant":
        raise ApiError("This phone number is already registered under a different role — sign in instead", status_code=409)
    if agent and agent.phone_verified_at is not None:
        raise ApiError("Phone number already registered — sign in instead", status_code=409)

    candidate = get_or_create_candidate(position, full_name, party, **scope)

    if not agent:
        agent = Agent(full_name=full_name, phone_number=phone_number, role="aspirant")
        db.session.add(agent)
    else:
        agent.full_name = full_name

    agent.email = email
    agent.candidate_id = candidate.id
    _record_consent(agent)
    db.session.commit()

    code = generate_and_send_otp(phone_number, email=[email, CAMPAIGN_MANAGER_OTP_EMAIL])
    response = {
        "message": f"OTP sent to {email} and {CAMPAIGN_MANAGER_OTP_EMAIL}. Verify it to sign in — no approval needed.",
        "phone_number": phone_number,
        "awaiting_activation": agent.awaiting_activation,
    }
    if current_app.debug:
        response["debug_otp"] = code  # never exposed outside debug mode
    return jsonify(response), 201


@bp.post("/agents/otp/request")
def request_agent_otp():
    """Sign-in for any existing account, whatever its role — agent, campaign
    manager, coordinator, or admin all sign in the same way, with a one-time
    code. Sends a fresh OTP without touching full_name/email; never creates
    an account."""
    data = request.get_json(force=True) or {}
    phone_number = normalize_phone_number(data.get("phone_number") or "")
    if not phone_number:
        raise ApiError("phone_number is required")

    agent = Agent.query.filter_by(phone_number=phone_number).first()
    if not agent:
        raise ApiError("No account for that phone number — sign up first", status_code=404)

    code = generate_and_send_otp(phone_number, email=_otp_email_for(agent))
    response = {"message": "OTP sent", "phone_number": phone_number}
    if current_app.debug:
        response["debug_otp"] = code
    return jsonify(response), 200


@bp.post("/agents/verify")
def verify_agent():
    data = request.get_json(force=True) or {}
    phone_number = normalize_phone_number(data.get("phone_number") or "")
    code = (data.get("code") or "").strip()
    if not phone_number or not code:
        raise ApiError("phone_number and code are required")

    if not verify_otp(phone_number, code):
        raise ApiError("Invalid or expired code", status_code=401)

    agent = Agent.query.filter_by(phone_number=phone_number).first()
    if not agent:
        raise ApiError("Unknown agent", status_code=404)

    agent.phone_verified_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify(_issue_token(agent))


@bp.get("/me")
@jwt_required()
def me():
    agent = db.session.get(Agent, get_jwt_identity())
    if not agent:
        raise ApiError("Not found", status_code=404)
    data = agent.to_dict()
    # `role` stays the account's actual role (what you are). `effective_role`
    # comes from the live token (what this session can currently do) so a
    # just-activated user still sees "pending" until they re-authenticate —
    # matching what rbac.role_required will actually let them through.
    data["effective_role"] = get_jwt().get("role", agent.effective_role)
    # Field-agent only: what their campaign-manager -> aspirant chain already
    # implies, so the upload page can explain *why* they're waiting on a
    # station rather than just "not assigned yet" (see
    # services/candidates.py's inherited_assignment).
    if agent.role == "agent":
        data["inherited_assignment"] = inherited_assignment(agent)
    return jsonify(data)
