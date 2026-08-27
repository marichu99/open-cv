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


def test_draft_rejected_when_form_header_doesnt_match_selected_station(client, app, geo, monkeypatch):
    """The station picker and the form the agent actually photographed are
    two independent things the UI can't otherwise reconcile — this is the
    one server-side guard against uploading a real form to the wrong
    station in the dropdown."""
    token, position_id = _login_agent(client, app, geo=geo)

    from app.services import cv_pipeline
    from app.api import submissions as submissions_api

    class WrongStationMock(cv_pipeline.MockExtractionService):
        def extract(self, image_path, position, declared_form_type):
            result = super().extract(image_path, position, declared_form_type)
            result.detected_location = cv_pipeline.DetectedLocation(
                county="Nyamira", constituency="Borabu", ward="Kiabonyoru",
                polling_station="Some Other Primary School",
            )
            return result

    monkeypatch.setattr(submissions_api, "get_extraction_service", lambda backend: WrongStationMock())

    resp = client.post(
        "/api/submissions/draft",
        data={"station_id": geo["station_id"], "position_id": position_id, "image": (fake_image_bytes(), "form.jpg")},
        headers=_auth_headers(token),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 422
    body = resp.get_json()
    assert "constituency" in body["error"]
    assert "ward" in body["error"]

    from app.models import FormSubmission

    with app.app_context():
        assert FormSubmission.query.count() == 0


def test_draft_succeeds_when_form_header_matches_selected_station(client, app, geo, monkeypatch):
    token, position_id = _login_agent(client, app, geo=geo)

    from app.services import cv_pipeline
    from app.api import submissions as submissions_api

    class MatchingStationMock(cv_pipeline.MockExtractionService):
        def extract(self, image_path, position, declared_form_type):
            result = super().extract(image_path, position, declared_form_type)
            result.detected_location = cv_pipeline.DetectedLocation(
                county="NYAMIRA", constituency="WEST MUGIRANGO", ward="NYANSIONGO",
                polling_station="Nyansiongo Pri Stream 1",
            )
            return result

    monkeypatch.setattr(submissions_api, "get_extraction_service", lambda backend: MatchingStationMock())

    resp = client.post(
        "/api/submissions/draft",
        data={"station_id": geo["station_id"], "position_id": position_id, "image": (fake_image_bytes(), "form.jpg")},
        headers=_auth_headers(token),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201


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


def test_blank_photo_rejected_before_ever_calling_extraction(client, app, geo, monkeypatch):
    """A solid-color/near-blank photo can't contain a legible form no
    matter what — it should be rejected locally, without spending an
    extraction-service call finding that out."""
    token, position_id = _login_agent(client, app, geo=geo)

    from app.api import submissions as submissions_api

    calls = []
    monkeypatch.setattr(
        submissions_api, "get_extraction_service",
        lambda backend: calls.append(backend) or None,
    )

    from PIL import Image

    blank = io.BytesIO()
    Image.new("L", (300, 300), 255).save(blank, format="PNG")
    blank.seek(0)

    resp = client.post(
        "/api/submissions/draft",
        data={"station_id": geo["station_id"], "position_id": position_id, "image": (blank, "blank.png")},
        headers=_auth_headers(token),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 422
    assert "blank" in resp.get_json()["error"].lower()
    assert calls == []  # extraction was never reached


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


def test_agent_can_correct_votes_before_finalize(client, app, geo, monkeypatch):
    """The agent's own extracted-preview edit path — corrections are applied
    the same way a coordinator's review corrections are, just before the
    submission ever leaves draft status."""
    token, position_id = _login_agent(client, app, geo=geo)

    from app.services import cv_pipeline
    from app.api import submissions as submissions_api

    class CleanMock(cv_pipeline.MockExtractionService):
        def extract(self, image_path, position, declared_form_type):
            result = super().extract(image_path, position, declared_form_type)
            for v in result.votes:
                v.confidence = 0.97
            result.warnings = []
            result.total_votes_cast = sum(v.votes for v in result.votes) + result.rejected_ballots
            return result

    monkeypatch.setattr(submissions_api, "get_extraction_service", lambda backend: CleanMock())
    resp = client.post(
        "/api/submissions/draft",
        data={"station_id": geo["station_id"], "position_id": position_id, "image": (fake_image_bytes(), "form.jpg")},
        headers=_auth_headers(token),
        content_type="multipart/form-data",
    )
    submission = resp.get_json()
    candidate_id = submission["vote_records"][0]["candidate_id"]
    original_votes = submission["vote_records"][0]["votes_detected"]
    corrected_votes = original_votes + 25

    final = client.post(
        f"/api/submissions/{submission['id']}/finalize",
        json={"corrections": [{"candidate_id": candidate_id, "votes_corrected": corrected_votes}]},
        headers=_auth_headers(token),
    )
    assert final.status_code == 200
    body = final.get_json()
    corrected = next(v for v in body["vote_records"] if v["candidate_id"] == candidate_id)
    assert corrected["effective_votes"] == corrected_votes
    assert corrected["manually_overridden"] is True


def test_second_submission_to_a_station_auto_supersedes_the_first_instead_of_double_counting(client, app, geo):
    """The agent has already seen and can correct the extracted figures
    before confirming, so their confirmation is authoritative — even over an
    earlier submission for the same station. finalize() should immediately
    supersede it (not park the new one in pending_review waiting on a
    coordinator), while making sure the station's votes are never counted
    twice."""
    token, position_id = _login_agent(client, app, geo=geo)

    def upload(image_suffix: bytes):
        data = {
            "station_id": geo["station_id"], "position_id": position_id,
            "image": (io.BytesIO(fake_image_bytes().read() + image_suffix), "form.jpg"),
        }
        resp = client.post(
            "/api/submissions/draft", data=data, headers=_auth_headers(token), content_type="multipart/form-data",
        )
        submission_id = resp.get_json()["id"]
        final = client.post(f"/api/submissions/{submission_id}/finalize", headers=_auth_headers(token))
        return final.get_json()

    first = upload(b"first")
    assert first["status"] == "auto_approved"

    # A second, genuinely different photo for the same station+form — e.g.
    # the agent retook the photo after the first one didn't look right.
    second = upload(b"second")
    assert second["status"] == "auto_approved"
    assert second["duplicate_of"] == first["id"]

    original = client.get(f"/api/submissions/{first['id']}", headers=_auth_headers(token)).get_json()
    assert original["status"] == "duplicate"
    assert original["duplicate_of"] == second["id"]


def test_coordinator_can_still_resolve_a_legacy_pending_review_duplicate(client, app, geo):
    """Rows already sitting in `pending_review` from before this behavior
    change (or created directly, e.g. a data fix) can still be resolved
    through the review endpoint — approving one supersedes whatever it was
    flagged as a duplicate of."""
    from app.extensions import db
    from app.models import Agent, ElectivePosition, FormSubmission

    token, position_id = _login_agent(client, app, geo=geo)
    resp = client.post(
        "/api/submissions/draft",
        data={"station_id": geo["station_id"], "position_id": position_id, "image": (fake_image_bytes(), "form.jpg")},
        headers=_auth_headers(token),
        content_type="multipart/form-data",
    )
    first = client.post(f"/api/submissions/{resp.get_json()['id']}/finalize", headers=_auth_headers(token)).get_json()
    assert first["status"] == "auto_approved"

    with app.app_context():
        agent_id = db.session.get(FormSubmission, first["id"]).agent_id
        legacy = FormSubmission(
            station_id=geo["station_id"], agent_id=agent_id, position_id=position_id, form_type="34A",
            image_path="x", image_sha256="legacy-dup", status="pending_review", duplicate_of=first["id"],
        )
        db.session.add(legacy)
        db.session.commit()
        legacy_id = str(legacy.id)

    admin = Agent(full_name="Admin", phone_number="+254700009997", role="admin", email="admin3.fixture@example.com")
    db.session.add(admin)
    db.session.commit()
    otp_req = client.post("/api/auth/agents/otp/request", json={"phone_number": "+254700009997"})
    otp = otp_req.get_json()["debug_otp"]
    login = client.post("/api/auth/agents/verify", json={"phone_number": "+254700009997", "code": otp})
    admin_token = login.get_json()["access_token"]

    review = client.post(
        f"/api/submissions/{legacy_id}/review", json={"action": "approve"}, headers=_auth_headers(admin_token),
    )
    assert review.status_code == 200
    assert review.get_json()["status"] == "manually_approved"

    original = client.get(f"/api/submissions/{first['id']}", headers=_auth_headers(admin_token)).get_json()
    assert original["status"] == "duplicate"
    assert original["duplicate_of"] == legacy_id


def test_flagged_submissions_still_count_toward_tally_but_show_in_discrepancies_grid(client, app, geo, monkeypatch):
    """Review no longer gates the tally: a submission counts (`auto_approved`)
    the moment the agent finalizes it, regardless of warnings or confidence.
    `?has_warnings=true` is the "Discrepancies" grid — a monitoring view, not
    an approval queue — and should surface anything the model itself flagged
    as ambiguous *or* that came in under the confidence threshold, while a
    clean, confident submission stays out of it."""
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

    class CleanMock(cv_pipeline.MockExtractionService):
        def extract(self, image_path, position, declared_form_type):
            result = super().extract(image_path, position, declared_form_type)
            for v in result.votes:
                v.confidence = 0.97
            result.total_votes_confidence = 0.97
            result.rejected_ballots_confidence = 0.97
            result.total_votes_cast = sum(v.votes for v in result.votes) + result.rejected_ballots
            result.warnings = []
            return result

    # Distinct stations for each upload: since finalize() now auto-approves
    # immediately, a second submission for the *same* station+form would
    # correctly get held as a likely duplicate — that's a different behavior
    # this test isn't exercising.
    from app.extensions import db
    from app.models import PollingStation

    def _extra_station(iebc_code):
        with app.app_context():
            station = PollingStation(ward_id=geo["ward_id"], iebc_code=iebc_code, name=f"Station {iebc_code}")
            db.session.add(station)
            db.session.commit()
            return str(station.id)

    def upload_and_finalize(mock_service, phone, station_id):
        token, position_id = _login_agent(client, app, phone=phone, geo=geo)
        monkeypatch.setattr(submissions_api, "get_extraction_service", lambda backend: mock_service)
        image = io.BytesIO(fake_image_bytes().read() + phone.encode())
        resp = client.post(
            "/api/submissions/draft",
            data={"station_id": station_id, "position_id": position_id, "image": (image, "form.jpg")},
            headers=_auth_headers(token),
            content_type="multipart/form-data",
        )
        submission_id = resp.get_json()["id"]
        final = client.post(f"/api/submissions/{submission_id}/finalize", headers=_auth_headers(token))
        assert final.get_json()["status"] == "auto_approved"
        return submission_id

    flagged_id = upload_and_finalize(FlaggedMock(), "+254722000200", geo["station_id"])
    low_conf_id = upload_and_finalize(LowConfidenceMock(), "+254722000201", _extra_station("WM102"))
    clean_id = upload_and_finalize(CleanMock(), "+254722000202", _extra_station("WM103"))

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
        "/api/submissions", query_string={"has_warnings": "true"}, headers=_auth_headers(admin_token),
    )
    assert flagged_only.status_code == 200
    ids = [s["id"] for s in flagged_only.get_json()]
    assert flagged_id in ids
    assert low_conf_id in ids
    assert clean_id not in ids

    all_approved = client.get(
        "/api/submissions", query_string={"status": "auto_approved"}, headers=_auth_headers(admin_token),
    )
    all_ids = [s["id"] for s in all_approved.get_json()]
    assert flagged_id in all_ids
    assert low_conf_id in all_ids
    assert clean_id in all_ids
