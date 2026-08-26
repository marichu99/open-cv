from datetime import datetime, timezone


def test_president_tally_sums_only_approved_34a(client, geo, app):
    from app.extensions import db
    from app.models import Agent, Candidate, ElectivePosition, FormSubmission, VoteRecord

    position_id = geo["positions"]["president"]

    with app.app_context():
        agent = Agent(full_name="Agent", phone_number="+254733000111", role="agent")
        agent.positions = [db.session.get(ElectivePosition, position_id)]
        db.session.add(agent)

        candidate_a = Candidate(position_id=position_id, full_name="Candidate A", normalized_name="CANDIDATE A")
        candidate_b = Candidate(position_id=position_id, full_name="Candidate B", normalized_name="CANDIDATE B")
        db.session.add_all([candidate_a, candidate_b])
        db.session.flush()
        candidate_a_id, candidate_b_id = str(candidate_a.id), str(candidate_b.id)

        approved = FormSubmission(
            station_id=geo["station_id"],
            agent_id=agent.id,
            position_id=position_id,
            form_type="34A",
            image_path="x",
            image_sha256="a1",
            status="auto_approved",
            total_votes_cast=210,
            rejected_ballots=10,
            ocr_confidence_avg=95,
            finalized_at=datetime.now(timezone.utc),
        )
        db.session.add(approved)
        db.session.flush()
        db.session.add(VoteRecord(submission_id=approved.id, candidate_id=candidate_a.id,
                                   votes_detected=150, field_confidence=95))
        db.session.add(VoteRecord(submission_id=approved.id, candidate_id=candidate_b.id,
                                   votes_detected=50, field_confidence=95))

        pending = FormSubmission(
            station_id=geo["station_id"],
            agent_id=agent.id,
            position_id=position_id,
            form_type="34A",
            image_path="x",
            image_sha256="a2",
            status="pending_review",
            total_votes_cast=999,
            rejected_ballots=0,
            ocr_confidence_avg=50,
        )
        db.session.add(pending)
        db.session.flush()
        db.session.add(VoteRecord(submission_id=pending.id, candidate_id=candidate_a.id,
                                   votes_detected=999, field_confidence=50))
        db.session.commit()

    resp = client.get(f"/api/tally/summary?position_id={position_id}")
    assert resp.status_code == 200
    body = resp.get_json()
    votes_by_candidate = {c["candidate_id"]: c["votes"] for c in body["candidates"]}
    assert votes_by_candidate[candidate_a_id] == 150  # pending_review excluded
    assert votes_by_candidate[candidate_b_id] == 50
    assert body["stations_reported"] == 1


def test_summary_requires_scope_for_county_level_position(client, geo):
    position_id = geo["positions"]["woman_representative"]
    resp = client.get(f"/api/tally/summary?position_id={position_id}")
    assert resp.status_code == 400


def test_positions_endpoint_lists_all_six(client, geo):
    resp = client.get("/api/tally/positions")
    assert resp.status_code == 200
    names = {p["name"] for p in resp.get_json()}
    assert names == {"president", "governor", "senator", "woman_representative", "member_of_parliament", "mca"}
