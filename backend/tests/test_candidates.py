def _otp_login(client, phone, full_name, role, email):
    from app.extensions import db
    from app.models import Agent

    agent = Agent(full_name=full_name, phone_number=phone, role=role, email=email)
    db.session.add(agent)
    db.session.commit()
    otp_req = client.post("/api/auth/agents/otp/request", json={"phone_number": phone})
    otp = otp_req.get_json()["debug_otp"]
    login = client.post("/api/auth/agents/verify", json={"phone_number": phone, "code": otp})
    return login.get_json()["access_token"]


def test_get_or_create_candidate_matches_name_variants_instead_of_duplicating(app, geo):
    from app.services.candidates import get_or_create_candidate

    with app.app_context():
        from app.models import ElectivePosition

        position = ElectivePosition.query.filter_by(id=geo["positions"]["president"]).first()

        first = get_or_create_candidate(position, "ODINGA RAILA")
        # A middle name present on a later scan and not the first — should
        # land on the same candidate, not fragment the vote count.
        fuller = get_or_create_candidate(position, "ODINGA RAILA AMOLO")
        assert fuller.id == first.id

        # Word order swapped — still the same token set, still a match.
        reordered = get_or_create_candidate(position, "RAILA ODINGA")
        assert reordered.id == first.id

        # A genuinely different candidate must NOT be merged just because
        # they share a surname.
        different = get_or_create_candidate(position, "ODINGA JOHN")
        assert different.id != first.id


def test_campaign_manager_can_seed_and_remove_candidates(client, app, geo):
    token = _otp_login(client, "+254700005001", "CM", "campaign_manager", "cm1@example.com")
    position_id = geo["positions"]["president"]

    create = client.post(
        "/api/candidates",
        json={"position_id": position_id, "full_name": "Ruto William Samoei", "party": "UDA"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create.status_code == 201
    candidate = create.get_json()
    assert candidate["full_name"] == "Ruto William Samoei"

    listing = client.get(f"/api/candidates?position_id={position_id}")
    assert any(c["id"] == candidate["id"] for c in listing.get_json())

    delete = client.delete(f"/api/candidates/{candidate['id']}", headers={"Authorization": f"Bearer {token}"})
    assert delete.status_code == 204
    listing_after = client.get(f"/api/candidates?position_id={position_id}")
    assert not any(c["id"] == candidate["id"] for c in listing_after.get_json())


def test_seeded_candidate_absorbs_later_extraction_variants(client, app, geo):
    """The exact scenario a campaign manager is solving: pre-seed the
    official name, then an agent's extraction of a slightly different
    reading of that same name should count against it, not create a rival
    row."""
    token = _otp_login(client, "+254700005002", "CM", "campaign_manager", "cm2@example.com")
    position_id = geo["positions"]["president"]

    create = client.post(
        "/api/candidates",
        json={"position_id": position_id, "full_name": "ODINGA RAILA AMOLO"},
        headers={"Authorization": f"Bearer {token}"},
    )
    seeded_id = create.get_json()["id"]

    with app.app_context():
        from app.models import ElectivePosition
        from app.services.candidates import get_or_create_candidate

        position = ElectivePosition.query.filter_by(id=position_id).first()
        matched = get_or_create_candidate(position, "ODINGA RAILA")
        assert str(matched.id) == seeded_id


def test_cannot_delete_candidate_with_recorded_votes(client, app, geo):
    from app.extensions import db
    from app.models import Agent, Candidate, FormSubmission, VoteRecord

    token = _otp_login(client, "+254700005003", "CM", "campaign_manager", "cm3@example.com")
    position_id = geo["positions"]["president"]

    with app.app_context():
        agent = Agent(full_name="Uploader", phone_number="+254700005004", role="agent")
        db.session.add(agent)
        db.session.flush()
        candidate = Candidate(position_id=position_id, full_name="Has Votes", normalized_name="HAS VOTES")
        db.session.add(candidate)
        db.session.flush()
        submission = FormSubmission(
            station_id=geo["station_id"], agent_id=agent.id, position_id=position_id, form_type="34A",
            image_path="x", image_sha256="cvcheck", status="draft",
        )
        db.session.add(submission)
        db.session.flush()
        db.session.add(VoteRecord(submission_id=submission.id, candidate_id=candidate.id, votes_detected=5,
                                   field_confidence=90))
        db.session.commit()
        candidate_id = str(candidate.id)

    resp = client.delete(f"/api/candidates/{candidate_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 409
