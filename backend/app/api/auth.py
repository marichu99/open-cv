from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt

from app.extensions import db
from app.models import Agent
from app.services.otp import generate_and_send_otp, verify_otp
from app.utils.errors import ApiError
from app.utils.phone import normalize_phone_number

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# Campaign managers can assign agents to any station/position, so every code
# — signup or sign-in, no matter who's asking — always goes to this one
# inbox too, on top of the campaign manager's own address: someone holding
# this inbox has to be able to see every code, even ones meant for someone
# else's account, so a rogue signup can't go unnoticed.
CAMPAIGN_MANAGER_OTP_EMAIL = "marichufx@gmail.com"


def _issue_token(agent: Agent):
    claims = {"role": agent.role, "full_name": agent.full_name}
    token = create_access_token(identity=str(agent.id), additional_claims=claims)
    return {"access_token": token, "agent": agent.to_dict()}


def _otp_email_for(agent: Agent) -> str | list[str]:
    """Every role signs in with a one-time code, emailed to the address on
    file — campaign managers additionally always get it at the fixed inbox
    above, so it's never solely in one person's control."""
    if not agent.email:
        raise ApiError(
            "No email on file for this account — ask an admin to add one before you can sign in",
            status_code=400,
        )
    if agent.role == "campaign_manager":
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
    /agents/otp/request instead. Station assignment is deliberately not
    accepted here — agents don't pick their own ward/station; a
    coordinator/admin assigns it afterwards via PATCH
    /api/agents/:id/assignment (see api/agents.py)."""
    data = request.get_json(force=True) or {}
    full_name = (data.get("full_name") or "").strip()
    phone_number = normalize_phone_number(data.get("phone_number") or "")
    email = (data.get("email") or "").strip().lower() or None
    if not full_name or not phone_number:
        raise ApiError("full_name and phone_number are required")
    _validate_and_check_email(email, phone_number)

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

    db.session.commit()

    code = generate_and_send_otp(phone_number, email=agent.email)
    response = {"message": "OTP sent", "phone_number": phone_number}
    if current_app.debug:
        response["debug_otp"] = code  # never exposed outside debug mode
    return jsonify(response), 201


@bp.post("/campaign_managers/register")
def register_campaign_manager():
    """Campaign manager signup. The OTP goes to the registrant's own email
    *and* to CAMPAIGN_MANAGER_OTP_EMAIL — the fixed inbox always sees it too,
    so a campaign manager account can never be signed into by someone who
    only controls one of the two addresses."""
    data = request.get_json(force=True) or {}
    full_name = (data.get("full_name") or "").strip()
    phone_number = normalize_phone_number(data.get("phone_number") or "")
    email = (data.get("email") or "").strip().lower() or None
    if not full_name or not phone_number or not email:
        raise ApiError("full_name, phone_number, and email are required")
    _validate_and_check_email(email, phone_number)

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
    db.session.commit()

    code = generate_and_send_otp(phone_number, email=[email, CAMPAIGN_MANAGER_OTP_EMAIL])
    response = {"message": f"OTP sent to {email} and {CAMPAIGN_MANAGER_OTP_EMAIL}", "phone_number": phone_number}
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

    from datetime import datetime, timezone

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
    data["role"] = get_jwt().get("role", agent.role)
    return jsonify(data)
