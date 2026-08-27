from app.extensions import db
from app.models import Agent


def _login_agent(client, phone="+254722000111"):
    reg = client.post("/api/auth/agents/register", json={"full_name": "J. Nyaboke", "phone_number": phone})
    otp = reg.get_json()["debug_otp"]
    verify = client.post("/api/auth/agents/verify", json={"phone_number": phone, "code": otp})
    return verify.get_json()["access_token"], verify.get_json()["agent"]["id"]


def _otp_login(client, app, *, full_name, phone_number, role, email):
    with app.app_context():
        agent = Agent(full_name=full_name, phone_number=phone_number, role=role, email=email)
        db.session.add(agent)
        db.session.commit()

    otp_req = client.post("/api/auth/agents/otp/request", json={"phone_number": phone_number})
    code = otp_req.get_json()["debug_otp"]
    verify = client.post("/api/auth/agents/verify", json={"phone_number": phone_number, "code": code})
    return verify.get_json()["access_token"]


def _login_campaign_manager(client, app):
    return _otp_login(
        client, app, full_name="Campaign Manager", phone_number="+254700008888",
        role="campaign_manager", email="campaign.manager.fixture@example.com",
    )


def _login_coordinator(client, app):
    """Coordinators review submissions but no longer manage agent assignment."""
    return _otp_login(
        client, app, full_name="Coordinator", phone_number="+254700007777",
        role="coordinator", email="coordinator.fixture@example.com",
    )


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_agent_cannot_list_or_assign(client):
    token, agent_id = _login_agent(client)

    listing = client.get("/api/agents", headers=_auth_headers(token))
    assert listing.status_code == 403

    assign = client.patch(
        f"/api/agents/{agent_id}/assignment",
        json={"assigned_station_id": None},
        headers=_auth_headers(token),
    )
    assert assign.status_code == 403


def test_coordinator_can_no_longer_manage_agents(client, app):
    """Agent assignment moved exclusively to campaign_manager — coordinator
    keeps submission moderation only (see api/review.py)."""
    _, agent_id = _login_agent(client)
    coordinator_token = _login_coordinator(client, app)

    listing = client.get("/api/agents", headers=_auth_headers(coordinator_token))
    assert listing.status_code == 403

    assign = client.patch(
        f"/api/agents/{agent_id}/assignment",
        json={"assigned_station_id": None},
        headers=_auth_headers(coordinator_token),
    )
    assert assign.status_code == 403


def test_campaign_manager_lists_and_assigns_agent(client, app, geo):
    _, agent_id = _login_agent(client)
    manager_token = _login_campaign_manager(client, app)

    listing = client.get("/api/agents", headers=_auth_headers(manager_token))
    assert listing.status_code == 200
    body = listing.get_json()
    assert len(body) == 1
    assert body[0]["assigned_station_id"] is None
    assert body[0]["assigned_station_name"] is None
    assert body[0]["position_ids"] == []

    woman_rep_id = geo["positions"]["woman_representative"]
    president_id = geo["positions"]["president"]
    assign = client.patch(
        f"/api/agents/{agent_id}/assignment",
        json={"assigned_station_id": geo["station_id"], "position_ids": [woman_rep_id, president_id]},
        headers=_auth_headers(manager_token),
    )
    assert assign.status_code == 200
    body = assign.get_json()
    assert body["assigned_station_id"] == geo["station_id"]
    assert body["assigned_station_name"]
    assert body["county_name"] == "Nyamira"
    assert body["constituency_name"] == "West Mugirango"
    assert body["ward_name"] == "Nyansiongo"
    # a single agent posted at one station commonly tracks several races there
    assert set(body["position_ids"]) == {woman_rep_id, president_id}
    assert set(body["position_names"]) == {"woman_representative", "president"}

    # drop back to just one race
    narrow = client.patch(
        f"/api/agents/{agent_id}/assignment",
        json={"position_ids": [woman_rep_id]},
        headers=_auth_headers(manager_token),
    )
    assert narrow.get_json()["position_ids"] == [woman_rep_id]

    # unassign everything
    clear = client.patch(
        f"/api/agents/{agent_id}/assignment",
        json={"assigned_station_id": None, "position_ids": []},
        headers=_auth_headers(manager_token),
    )
    body = clear.get_json()
    assert body["assigned_station_id"] is None
    assert body["position_ids"] == []


def test_assign_rejects_unknown_station(client, app):
    _, agent_id = _login_agent(client)
    manager_token = _login_campaign_manager(client, app)

    resp = client.patch(
        f"/api/agents/{agent_id}/assignment",
        json={"assigned_station_id": "00000000-0000-0000-0000-000000000000"},
        headers=_auth_headers(manager_token),
    )
    assert resp.status_code == 400


def test_assign_rejects_unknown_position(client, app):
    _, agent_id = _login_agent(client)
    manager_token = _login_campaign_manager(client, app)

    resp = client.patch(
        f"/api/agents/{agent_id}/assignment",
        json={"position_ids": ["00000000-0000-0000-0000-000000000000"]},
        headers=_auth_headers(manager_token),
    )
    assert resp.status_code == 400
