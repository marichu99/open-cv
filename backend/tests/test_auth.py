def test_agent_register_and_verify_flow(client):
    resp = client.post(
        "/api/auth/agents/register",
        json={"full_name": "J. Nyaboke", "phone_number": "+254722000111"},
    )
    assert resp.status_code == 201
    otp = resp.get_json()["debug_otp"]

    bad = client.post(
        "/api/auth/agents/verify",
        json={"phone_number": "+254722000111", "code": "000000"},
    )
    assert bad.status_code == 401

    ok = client.post(
        "/api/auth/agents/verify",
        json={"phone_number": "+254722000111", "code": otp},
    )
    assert ok.status_code == 200
    body = ok.get_json()
    assert "access_token" in body
    assert body["agent"]["phone_verified"] is True


def test_me_requires_token(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_agent_signup_ignores_self_assigned_station(client, geo):
    """Agents can't assign their own station at signup — a coordinator/admin
    does it afterwards via PATCH /api/agents/:id/assignment (test_agents.py)."""
    resp = client.post(
        "/api/auth/agents/register",
        json={
            "full_name": "A. Kemunto",
            "phone_number": "+254733000222",
            "assigned_station_id": geo["station_id"],
        },
    )
    assert resp.status_code == 201
    otp = resp.get_json()["debug_otp"]

    verify = client.post(
        "/api/auth/agents/verify",
        json={"phone_number": "+254733000222", "code": otp},
    )
    assert verify.status_code == 200
    assert verify.get_json()["agent"]["assigned_station_id"] is None
    assert verify.get_json()["agent"]["role"] == "agent"


def test_signup_with_email_sends_via_smtp(client, monkeypatch):
    sent = {}

    def fake_send(to_email, code):
        sent["to_email"] = to_email
        sent["code"] = code

    monkeypatch.setattr("app.services.otp._dispatch_email", fake_send)

    resp = client.post(
        "/api/auth/agents/register",
        json={
            "full_name": "E. Mail",
            "phone_number": "+254733000555",
            "email": "e.mail@example.com",
        },
    )
    assert resp.status_code == 201
    otp = resp.get_json()["debug_otp"]
    assert sent == {"to_email": "e.mail@example.com", "code": otp}

    verify = client.post(
        "/api/auth/agents/verify",
        json={"phone_number": "+254733000555", "code": otp},
    )
    assert verify.get_json()["agent"]["email"] == "e.mail@example.com"


def test_signup_rejects_duplicate_email(client):
    client.post(
        "/api/auth/agents/register",
        json={"full_name": "First", "phone_number": "+254733000556", "email": "dupe@example.com"},
    )
    resp = client.post(
        "/api/auth/agents/register",
        json={"full_name": "Second", "phone_number": "+254733000557", "email": "dupe@example.com"},
    )
    assert resp.status_code == 400


def test_returning_agent_otp_request_and_login(client, monkeypatch):
    monkeypatch.setattr("app.services.otp._dispatch_email", lambda *a, **k: None)

    signup = client.post(
        "/api/auth/agents/register",
        json={"full_name": "Returning Agent", "phone_number": "+254733000558", "email": "returning@example.com"},
    )
    otp = signup.get_json()["debug_otp"]
    client.post("/api/auth/agents/verify", json={"phone_number": "+254733000558", "code": otp})

    # unknown number can't request a login OTP
    unknown = client.post("/api/auth/agents/otp/request", json={"phone_number": "+254700999999"})
    assert unknown.status_code == 404

    # doesn't touch full_name/email, unlike /agents/register
    again = client.post("/api/auth/agents/otp/request", json={"phone_number": "+254733000558"})
    assert again.status_code == 200
    new_otp = again.get_json()["debug_otp"]

    login = client.post(
        "/api/auth/agents/verify",
        json={"phone_number": "+254733000558", "code": new_otp},
    )
    assert login.status_code == 200
    assert login.get_json()["agent"]["full_name"] == "Returning Agent"


def test_agent_otp_request_requires_email_on_file(client):
    """An agent record with no email has no way to receive a code — the
    endpoint should say so clearly rather than silently doing nothing."""
    signup = client.post(
        "/api/auth/agents/register",
        json={"full_name": "No Email", "phone_number": "+254733000559"},
    )
    otp = signup.get_json()["debug_otp"]
    client.post("/api/auth/agents/verify", json={"phone_number": "+254733000559", "code": otp})

    resp = client.post("/api/auth/agents/otp/request", json={"phone_number": "+254733000559"})
    assert resp.status_code == 400


def test_campaign_manager_signup_requires_email(client):
    resp = client.post(
        "/api/auth/campaign_managers/register",
        json={"full_name": "No Email", "phone_number": "+254733000699"},
    )
    assert resp.status_code == 400


def test_campaign_manager_signup_otp_goes_to_own_email_and_fixed_inbox(client, monkeypatch):
    sent = []

    def fake_send(to_email, code):
        sent.append({"to_email": to_email, "code": code})

    monkeypatch.setattr("app.services.otp._dispatch_email", fake_send)

    resp = client.post(
        "/api/auth/campaign_managers/register",
        json={"full_name": "New Manager", "phone_number": "+254733000700", "email": "new.manager@example.com"},
    )
    assert resp.status_code == 201
    otp = resp.get_json()["debug_otp"]
    assert sent == [
        {"to_email": "new.manager@example.com", "code": otp},
        {"to_email": "marichufx@gmail.com", "code": otp},
    ]

    verify = client.post(
        "/api/auth/agents/verify",
        json={"phone_number": "+254733000700", "code": otp},
    )
    assert verify.status_code == 200
    body = verify.get_json()
    assert body["agent"]["role"] == "campaign_manager"
    assert body["agent"]["email"] == "new.manager@example.com"

    # returning campaign managers also always get their code at both addresses
    sent.clear()
    again = client.post("/api/auth/agents/otp/request", json={"phone_number": "+254733000700"})
    assert again.status_code == 200
    new_otp = again.get_json()["debug_otp"]
    assert sent == [
        {"to_email": "new.manager@example.com", "code": new_otp},
        {"to_email": "marichufx@gmail.com", "code": new_otp},
    ]

    login = client.post(
        "/api/auth/agents/verify",
        json={"phone_number": "+254733000700", "code": new_otp},
    )
    assert login.status_code == 200
    assert login.get_json()["agent"]["role"] == "campaign_manager"


def test_cannot_become_campaign_manager_after_starting_agent_signup(client):
    """A phone number commits to one role at signup — even before
    verification — so an abandoned agent signup can't be reclaimed as a
    campaign manager (or vice versa) with the same number."""
    agent_signup = client.post(
        "/api/auth/agents/register",
        json={"full_name": "Abandoned Agent", "phone_number": "+254733000800"},
    )
    assert agent_signup.status_code == 201  # unverified — never completes

    cm_attempt = client.post(
        "/api/auth/campaign_managers/register",
        json={"full_name": "Takeover Attempt", "phone_number": "+254733000800", "email": "takeover@example.com"},
    )
    assert cm_attempt.status_code == 409


def test_cannot_become_agent_after_starting_campaign_manager_signup(client):
    cm_signup = client.post(
        "/api/auth/campaign_managers/register",
        json={"full_name": "Abandoned Manager", "phone_number": "+254733000801", "email": "abandoned.manager@example.com"},
    )
    assert cm_signup.status_code == 201  # unverified — never completes

    agent_attempt = client.post(
        "/api/auth/agents/register",
        json={"full_name": "Takeover Attempt", "phone_number": "+254733000801"},
    )
    assert agent_attempt.status_code == 409


def test_cannot_reregister_verified_phone(client):
    first = client.post(
        "/api/auth/agents/register",
        json={"full_name": "First", "phone_number": "+254733000444"},
    )
    otp = first.get_json()["debug_otp"]
    client.post("/api/auth/agents/verify", json={"phone_number": "+254733000444", "code": otp})

    again = client.post(
        "/api/auth/agents/register",
        json={"full_name": "Takeover", "phone_number": "+254733000444"},
    )
    assert again.status_code == 409


def test_phone_number_normalized_across_formats(client):
    """A number registered as +2547XXXXXXXX must still resolve when typed
    back in local (07XXXXXXXX) or bare (7XXXXXXXX) format — these all mean
    the same phone number, they just look different as raw strings."""
    reg = client.post(
        "/api/auth/agents/register",
        json={"full_name": "Format Test", "phone_number": "+254733000900", "email": "format.test@example.com"},
    )
    assert reg.status_code == 201
    otp = reg.get_json()["debug_otp"]
    client.post("/api/auth/agents/verify", json={"phone_number": "+254733000900", "code": otp})

    for local_variant in ["0733000900", "733000900", "254733000900"]:
        resp = client.post("/api/auth/agents/otp/request", json={"phone_number": local_variant})
        assert resp.status_code == 200, f"failed for {local_variant!r}: {resp.get_json()}"


# --- Phase 0: campaign-manager signup is open, but the role is inert until
# --- an admin activates it (see app/models/agent.py, api/agents.py).


def _register_campaign_manager(client, phone="+254733000800", email="cm@example.com"):
    resp = client.post(
        "/api/auth/campaign_managers/register",
        json={"full_name": "Self Signup", "phone_number": phone, "email": email},
    )
    assert resp.status_code == 201
    otp = resp.get_json()["debug_otp"]
    verify = client.post("/api/auth/agents/verify", json={"phone_number": phone, "code": otp})
    assert verify.status_code == 200
    return verify.get_json()


def _make_admin(app, phone="+254700000001", email="admin@example.com"):
    """An already-activated admin, the way the migration backfills existing rows."""
    from datetime import datetime, timezone

    from app.extensions import db
    from app.models import Agent

    with app.app_context():
        admin = Agent(
            full_name="County Admin",
            phone_number=phone,
            email=email,
            role="admin",
            activated_at=datetime.now(timezone.utc),
        )
        db.session.add(admin)
        db.session.commit()
        return str(admin.id)


def _login(client, phone):
    otp = client.post("/api/auth/agents/otp/request", json={"phone_number": phone}).get_json()["debug_otp"]
    return client.post(
        "/api/auth/agents/verify", json={"phone_number": phone, "code": otp}
    ).get_json()["access_token"]


def test_self_registered_campaign_manager_gets_an_inert_pending_token(client):
    """The whole point of the gate: signing up must not hand an anonymous
    caller the ability to reassign agents or dump every agent's PII."""
    body = _register_campaign_manager(client)

    assert body["agent"]["role"] == "campaign_manager"       # what it is
    assert body["agent"]["effective_role"] == "pending"      # what it can do
    assert body["agent"]["awaiting_activation"] is True
    assert body["agent"]["activated_at"] is None

    headers = {"Authorization": f"Bearer {body['access_token']}"}
    assert client.get("/api/agents", headers=headers).status_code == 403
    assert client.post("/api/candidates", json={}, headers=headers).status_code == 403


def test_admin_activation_promotes_the_account_on_next_login(client, app):
    body = _register_campaign_manager(client)
    cm_id = body["agent"]["id"]
    _make_admin(app)
    admin_headers = {"Authorization": f"Bearer {_login(client, '+254700000001')}"}

    activate = client.patch(
        f"/api/agents/{cm_id}/activation", json={"activated": True}, headers=admin_headers
    )
    assert activate.status_code == 200
    assert activate.get_json()["awaiting_activation"] is False

    # The privilege arrives with the NEXT token — the old one still says pending,
    # because there is no revocation list yet (Phase 3.4).
    assert client.get("/api/agents", headers={"Authorization": f"Bearer {body['access_token']}"}).status_code == 403
    assert client.get("/api/agents", headers={"Authorization": f"Bearer {_login(client, '+254733000800')}"}).status_code == 200


def test_a_pending_campaign_manager_cannot_activate_themselves(client):
    """Otherwise the gate is just self-service with extra steps."""
    body = _register_campaign_manager(client)
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    resp = client.patch(f"/api/agents/{body['agent']['id']}/activation", json={"activated": True}, headers=headers)
    assert resp.status_code == 403


def test_an_activated_campaign_manager_cannot_activate_another(client, app):
    """Activation is admin-only; a campaign manager promoting peers would
    re-open the same escalation path."""
    first = _register_campaign_manager(client)
    second = _register_campaign_manager(client, phone="+254733000801", email="cm2@example.com")

    _make_admin(app)
    client.patch(
        f"/api/agents/{first['agent']['id']}/activation",
        json={"activated": True},
        headers={"Authorization": f"Bearer {_login(client, '+254700000001')}"},
    )

    cm_headers = {"Authorization": f"Bearer {_login(client, '+254733000800')}"}
    resp = client.patch(
        f"/api/agents/{second['agent']['id']}/activation", json={"activated": True}, headers=cm_headers
    )
    assert resp.status_code == 403


def test_pre_existing_accounts_keep_their_role(client, app):
    """Guards the migration's backfill. Every row that existed before
    c3f1a72b9d84 is stamped activated_at=now(); without that, this deploy
    would lock every current admin and campaign manager out of production."""
    _make_admin(app)
    token = _login(client, "+254700000001")
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.get_json()["effective_role"] == "admin"
    assert client.get("/api/agents", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_agents_are_not_subject_to_the_activation_gate(client):
    """Field agents are gated by station/position assignment instead — gating
    them twice would stall onboarding on election morning."""
    resp = client.post(
        "/api/auth/agents/register",
        json={"full_name": "Field Agent", "phone_number": "+254722000999"},
    )
    otp = resp.get_json()["debug_otp"]
    body = client.post(
        "/api/auth/agents/verify", json={"phone_number": "+254722000999", "code": otp}
    ).get_json()
    assert body["agent"]["effective_role"] == "agent"
    assert body["agent"]["awaiting_activation"] is False


def test_otp_code_is_not_logged_when_debug_is_off(client, app, caplog):
    """Regression for the cheapest full-compromise path in the system: the
    code used to be written to INFO unconditionally, and app/__init__.py's
    basicConfig(level=INFO) sends INFO to Cloud Logging with DEBUG off — so
    any holder of roles/logging.viewer could sign in as anyone."""
    import logging

    app.config["DEBUG"] = False
    with caplog.at_level(logging.INFO, logger="tally333.otp"):
        client.post(
            "/api/auth/agents/register",
            json={"full_name": "Quiet Log", "phone_number": "+254722000888"},
        )

    messages = [r.getMessage() for r in caplog.records]
    assert any("OTP issued for" in m for m in messages), messages
    from app.models.agent import OtpCode

    with app.app_context():
        code = OtpCode.query.filter_by(phone_number="+254722000888").first().code
    assert not any(code in m for m in messages), "the OTP code leaked into the logs"
