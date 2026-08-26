import io

from tests.conftest import fake_image_bytes, fake_pdf_bytes


def _login_agent(client, app, phone="+254722000111", position_name="woman_representative", geo=None):
    reg = client.post("/api/auth/agents/register", json={"full_name": "J. Nyaboke", "phone_number": phone})
    otp = reg.get_json()["debug_otp"]
    verify = client.post("/api/auth/agents/verify", json={"phone_number": phone, "code": otp})
    token = verify.get_json()["access_token"]
    agent_id = verify.get_json()["agent"]["id"]

    position_id = None
    # A campaign manager assigns this in the real flow (see api/agents.py) —
    # set it directly here so submission tests don't need the full RBAC dance.
    if geo:
        from app.extensions import db
        from app.models import Agent, ElectivePosition

        position_id = geo["positions"][position_name]
        with app.app_context():
            agent = db.session.get(Agent, agent_id)
            agent.positions = [db.session.get(ElectivePosition, position_id)]
            db.session.commit()

    return token, position_id


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_draft_then_finalize_auto_approves_when_confident(client, app, geo, monkeypatch):
    token, position_id = _login_agent(client, app, geo=geo)

    # Force a clean, high-confidence, arithmetically-consistent extraction.
    from app.services import cv_pipeline

    class CleanMock(cv_pipeline.MockExtractionService):
        def extract(self, image_path, position, declared_form_type):
            result = super().extract(image_path, position, declared_form_type)
            for v in result.votes:
                v.confidence = 0.97
            result.total_votes_confidence = 0.97
            result.rejected_ballots_confidence = 0.97
            result.warnings = []
            result.total_votes_cast = sum(v.votes for v in result.votes) + result.rejected_ballots
            return result

    from app.api import submissions as submissions_api

    monkeypatch.setattr(submissions_api, "get_extraction_service", lambda backend: CleanMock())

    resp = client.post(
        "/api/submissions/draft",
        data={
            "station_id": geo["station_id"],
            "position_id": position_id,
            "image": (fake_image_bytes(), "form.jpg"),
        },
        headers=_auth_headers(token),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    submission = resp.get_json()
    assert submission["status"] == "draft"
    assert submission["form_type"] == "39A"  # woman_representative's form series + station-level letter
    assert len(submission["vote_records"]) == 4  # MockExtractionService's fixed candidate names

    final = client.post(f"/api/submissions/{submission['id']}/finalize", headers=_auth_headers(token))
    assert final.status_code == 200
    assert final.get_json()["status"] == "auto_approved"


def test_submission_requires_assigned_position(client, app):
    token, _ = _login_agent(client, app)  # no geo -> no position assigned
    resp = client.post(
        "/api/submissions/draft",
        data={"station_id": "00000000-0000-0000-0000-000000000000", "image": (fake_image_bytes(), "form.jpg")},
        headers=_auth_headers(token),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 403


def test_submission_rejects_position_not_assigned_to_agent(client, app, geo):
    token, _ = _login_agent(client, app, geo=geo, position_name="woman_representative")
    other_position_id = geo["positions"]["president"]
    resp = client.post(
        "/api/submissions/draft",
        data={
            "station_id": geo["station_id"],
            "position_id": other_position_id,
            "image": (fake_image_bytes(), "form.jpg"),
        },
        headers=_auth_headers(token),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 403


def test_agent_with_multiple_positions_picks_one_per_upload(client, app, geo):
    from app.extensions import db
    from app.models import Agent, ElectivePosition

    token, _ = _login_agent(client, app, geo=geo, position_name="woman_representative")
    president_id = geo["positions"]["president"]

    # simulate the campaign manager assigning a second race to the same agent
    with app.app_context():
        agent = Agent.query.filter_by(phone_number="+254722000111").first()
        agent.positions = list(agent.positions) + [db.session.get(ElectivePosition, president_id)]
        db.session.commit()

    resp = client.post(
        "/api/submissions/draft",
        data={
            "station_id": geo["station_id"],
            "position_id": president_id,
            "image": (fake_image_bytes(), "form.jpg"),
        },
        headers=_auth_headers(token),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    assert resp.get_json()["form_type"] == "34A"  # president's series, not woman_representative's


def test_duplicate_exact_image_rejected(client, app, geo):
    token, position_id = _login_agent(client, app, geo=geo)
    payload = {"station_id": geo["station_id"], "position_id": position_id, "image": (fake_image_bytes(), "form.jpg")}
    first = client.post(
        "/api/submissions/draft", data=payload, headers=_auth_headers(token), content_type="multipart/form-data"
    )
    assert first.status_code == 201

    payload2 = {"station_id": geo["station_id"], "position_id": position_id, "image": (fake_image_bytes(), "form.jpg")}
    second = client.post(
        "/api/submissions/draft", data=payload2, headers=_auth_headers(token), content_type="multipart/form-data"
    )
    assert second.status_code == 409


def test_pdf_upload_is_converted_to_image(client, app, geo):
    token, position_id = _login_agent(client, app, geo=geo)
    resp = client.post(
        "/api/submissions/draft",
        data={
            "station_id": geo["station_id"],
            "position_id": position_id,
            "image": (fake_pdf_bytes(), "form.pdf"),
        },
        headers=_auth_headers(token),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    submission = resp.get_json()
    assert submission["image_url"].endswith("/image")

    image = client.get(f"/api/submissions/{submission['id']}/image", headers=_auth_headers(token))
    assert image.status_code == 200
    assert image.data[:8] == b"\x89PNG\r\n\x1a\n"  # stored as PNG, not the original PDF bytes


def test_invalid_pdf_upload_is_rejected(client, app, geo):
    token, position_id = _login_agent(client, app, geo=geo)
    resp = client.post(
        "/api/submissions/draft",
        data={
            "station_id": geo["station_id"],
            "position_id": position_id,
            "image": (io.BytesIO(b"not-a-real-pdf"), "form.pdf"),
        },
        headers=_auth_headers(token),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_admin_can_correct_and_approve(client, app, geo):
    token, position_id = _login_agent(client, app, geo=geo)
    resp = client.post(
        "/api/submissions/draft",
        data={"station_id": geo["station_id"], "position_id": position_id, "image": (fake_image_bytes(), "form.jpg")},
        headers=_auth_headers(token),
        content_type="multipart/form-data",
    )
    submission = resp.get_json()
    submission_id = submission["id"]
    client.post(f"/api/submissions/{submission_id}/finalize", headers=_auth_headers(token))

    # Seed an admin account directly and sign in via OTP, same as everyone else.
    from app.extensions import db
    from app.models import Agent

    admin = Agent(full_name="Admin", phone_number="+254700009999", role="admin", email="admin.fixture@example.com")
    db.session.add(admin)
    db.session.commit()

    otp_req = client.post("/api/auth/agents/otp/request", json={"phone_number": "+254700009999"})
    otp = otp_req.get_json()["debug_otp"]
    login = client.post("/api/auth/agents/verify", json={"phone_number": "+254700009999", "code": otp})
    admin_token = login.get_json()["access_token"]

    candidate_id = submission["vote_records"][0]["candidate_id"]
    review = client.post(
        f"/api/submissions/{submission_id}/review",
        json={"action": "approve", "corrections": [{"candidate_id": candidate_id, "votes_corrected": 500}]},
        headers=_auth_headers(admin_token),
    )
    assert review.status_code == 200
    body = review.get_json()
    assert body["status"] == "manually_approved"
    corrected = next(v for v in body["vote_records"] if v["candidate_id"] == candidate_id)
    assert corrected["effective_votes"] == 500
    assert corrected["manually_overridden"] is True


def test_list_submissions_can_filter_to_flagged_discrepancies(client, app, geo, monkeypatch):
    """`?has_warnings=true` is the "Discrepancies" tab in the moderation UI —
    it should only surface submissions Claude Vision itself flagged as
    ambiguous, not every pending-review submission (e.g. one that's merely
    low-confidence but had nothing specifically flagged)."""
    from app.services import cv_pipeline
    from app.api import submissions as submissions_api

    class FlaggedMock(cv_pipeline.MockExtractionService):
        def extract(self, image_path, position, declared_form_type):
            result = super().extract(image_path, position, declared_form_type)
            for v in result.votes:
                v.confidence = 0.97
            result.total_votes_cast = sum(v.votes for v in result.votes) + result.rejected_ballots
            result.warnings = ["Row 2 of Polling Station Counts is ambiguous — reads as '600' or '000'"]
            return result

    class LowConfidenceMock(cv_pipeline.MockExtractionService):
        def extract(self, image_path, position, declared_form_type):
            result = super().extract(image_path, position, declared_form_type)
            for v in result.votes:
                v.confidence = 0.5
            result.total_votes_confidence = 0.5
            result.total_votes_cast = sum(v.votes for v in result.votes) + result.rejected_ballots
            result.warnings = []
            return result

    def upload_and_finalize(mock_service, phone):
        token, position_id = _login_agent(client, app, phone=phone, geo=geo)
        monkeypatch.setattr(submissions_api, "get_extraction_service", lambda backend: mock_service)
        # distinct bytes per upload — the dedup guard rejects a second
        # identical image for the same station/form_type
        image = io.BytesIO(fake_image_bytes().read() + phone.encode())
        resp = client.post(
            "/api/submissions/draft",
            data={"station_id": geo["station_id"], "position_id": position_id, "image": (image, "form.jpg")},
            headers=_auth_headers(token),
            content_type="multipart/form-data",
        )
        submission_id = resp.get_json()["id"]
        client.post(f"/api/submissions/{submission_id}/finalize", headers=_auth_headers(token))
        return submission_id

    flagged_id = upload_and_finalize(FlaggedMock(), "+254722000200")
    low_conf_id = upload_and_finalize(LowConfidenceMock(), "+254722000201")

    from app.extensions import db
    from app.models import Agent

    admin = Agent(full_name="Admin", phone_number="+254700009998", role="admin", email="admin2.fixture@example.com")
    db.session.add(admin)
    db.session.commit()
    otp_req = client.post("/api/auth/agents/otp/request", json={"phone_number": "+254700009998"})
    otp = otp_req.get_json()["debug_otp"]
    login = client.post("/api/auth/agents/verify", json={"phone_number": "+254700009998", "code": otp})
    admin_token = login.get_json()["access_token"]

    flagged_only = client.get(
        "/api/submissions", query_string={"status": "pending_review", "has_warnings": "true"},
        headers=_auth_headers(admin_token),
    )
    assert flagged_only.status_code == 200
    ids = [s["id"] for s in flagged_only.get_json()]
    assert flagged_id in ids
    assert low_conf_id not in ids

    all_pending = client.get(
        "/api/submissions", query_string={"status": "pending_review"}, headers=_auth_headers(admin_token),
    )
    all_ids = [s["id"] for s in all_pending.get_json()]
    assert flagged_id in all_ids
    assert low_conf_id in all_ids
