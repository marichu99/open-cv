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


def _seed_approved(app, position_id, candidate_id, station_id, finalized_at, votes, sha, stream_number=1):
    from app.extensions import db
    from app.models import Agent, ElectivePosition, FormSubmission, VoteRecord

    with app.app_context():
        agent = Agent.query.filter_by(phone_number="+254733000222").first()
        if not agent:
            agent = Agent(full_name="Timeseries Agent", phone_number="+254733000222", role="agent")
            agent.positions = [db.session.get(ElectivePosition, position_id)]
            db.session.add(agent)
            db.session.flush()
        submission = FormSubmission(
            station_id=station_id, agent_id=agent.id, position_id=position_id, form_type="34A",
            image_path="x", image_sha256=sha, status="auto_approved", total_votes_cast=votes,
            rejected_ballots=0, ocr_confidence_avg=95, finalized_at=finalized_at, stream_number=stream_number,
        )
        db.session.add(submission)
        db.session.flush()
        db.session.add(VoteRecord(submission_id=submission.id, candidate_id=candidate_id,
                                   votes_detected=votes, field_confidence=95))
        db.session.commit()
        return str(submission.id)


def test_timeseries_auto_picks_a_fine_granularity_for_a_short_reporting_window(client, app, geo):
    from app.extensions import db
    from app.models import Candidate

    position_id = geo["positions"]["president"]
    with app.app_context():
        candidate = Candidate(position_id=position_id, full_name="Candidate A", normalized_name="CANDIDATE A")
        db.session.add(candidate)
        db.session.commit()
        candidate_id = candidate.id

    _seed_approved(app, position_id, candidate_id, geo["station_id"], datetime.now(timezone.utc), 10, "ts1")

    resp = client.get(f"/api/tally/timeseries?position_id={position_id}")
    assert resp.status_code == 200
    # A single-moment reporting window is well under the 5-minute cutoff for "second".
    assert resp.get_json()["granularity"] == "second"


def test_timeseries_granularity_can_be_overridden_explicitly(client, app, geo):
    from app.extensions import db
    from app.models import Candidate

    position_id = geo["positions"]["president"]
    with app.app_context():
        candidate = Candidate(position_id=position_id, full_name="Candidate A", normalized_name="CANDIDATE A")
        db.session.add(candidate)
        db.session.commit()
        candidate_id = candidate.id

    _seed_approved(app, position_id, candidate_id, geo["station_id"], datetime.now(timezone.utc), 10, "ts2")

    resp = client.get(f"/api/tally/timeseries?position_id={position_id}&granularity=day")
    assert resp.status_code == 200
    assert resp.get_json()["granularity"] == "day"


def test_votes_by_station_lists_one_row_per_station_most_recent_first(client, app, geo):
    from app.extensions import db
    from app.models import Candidate, PollingStation

    position_id = geo["positions"]["president"]
    with app.app_context():
        candidate = Candidate(position_id=position_id, full_name="Candidate A", normalized_name="CANDIDATE A")
        db.session.add(candidate)
        db.session.flush()
        second_station = PollingStation(ward_id=geo["ward_id"], iebc_code="WM999", name="Second Station")
        db.session.add(second_station)
        db.session.commit()
        candidate_id, second_station_id = str(candidate.id), str(second_station.id)

    older = datetime(2026, 1, 1, tzinfo=timezone.utc)
    newer = datetime(2026, 1, 2, tzinfo=timezone.utc)
    _seed_approved(app, position_id, candidate_id, geo["station_id"], older, 100, "bystation1")
    _seed_approved(app, position_id, candidate_id, second_station_id, newer, 50, "bystation2")

    resp = client.get(f"/api/tally/by_station?position_id={position_id}")
    assert resp.status_code == 200
    body = resp.get_json()
    station_names_in_order = [s["station_name"] for s in body["stations"]]
    assert station_names_in_order == ["Second Station", "Nyansiongo Pri Stream 1"]  # most recent first
    assert body["stations"][0]["votes"][candidate_id] == 50
    assert body["stations"][1]["votes"][candidate_id] == 100


def test_votes_by_station_shows_a_separate_row_per_stream_of_the_same_station(client, app, geo):
    """Two streams of the same polling station both tallied — see
    test_submissions.py's test_different_streams_of_the_same_station_both_count_instead_of_superseding
    for the finalize()-level guarantee this display relies on."""
    from app.extensions import db
    from app.models import Candidate

    position_id = geo["positions"]["president"]
    with app.app_context():
        candidate = Candidate(position_id=position_id, full_name="Candidate A", normalized_name="CANDIDATE A")
        db.session.add(candidate)
        db.session.commit()
        candidate_id = str(candidate.id)

    older = datetime(2026, 1, 1, tzinfo=timezone.utc)
    newer = datetime(2026, 1, 2, tzinfo=timezone.utc)
    _seed_approved(app, position_id, candidate_id, geo["station_id"], older, 100, "stream1", stream_number=1)
    _seed_approved(app, position_id, candidate_id, geo["station_id"], newer, 50, "stream3", stream_number=3)

    resp = client.get(f"/api/tally/by_station?position_id={position_id}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["stations"]) == 2
    stream_numbers = {s["stream_number"] for s in body["stations"]}
    assert stream_numbers == {1, 3}
    for s in body["stations"]:
        assert s["station_id"] == geo["station_id"]


def test_valid_groupings_depend_on_position_level(app, geo):
    from app.models import ElectivePosition
    from app.services.tally_service import valid_groupings

    with app.app_context():
        from app.extensions import db

        president = db.session.get(ElectivePosition, geo["positions"]["president"])
        governor = db.session.get(ElectivePosition, geo["positions"]["governor"])
        mp = db.session.get(ElectivePosition, geo["positions"]["member_of_parliament"])
        mca = db.session.get(ElectivePosition, geo["positions"]["mca"])

        assert valid_groupings(president) == ["county", "constituency", "ward", "station"]
        assert valid_groupings(governor) == ["constituency", "ward", "station"]
        assert valid_groupings(mp) == ["ward", "station"]
        assert valid_groupings(mca) == ["station"]


def test_by_group_rejects_a_grouping_that_collapses_to_one_row(client, geo):
    # MCA is already ward-scoped — grouping "by ward" would just repeat the Totals card.
    resp = client.get(
        f"/api/tally/by_group?position_id={geo['positions']['mca']}"
        f"&scope_id={geo['ward_id']}&level=ward"
    )
    assert resp.status_code == 400


def test_votes_by_group_aggregates_stations_within_the_same_ward(client, app, geo):
    from app.extensions import db
    from app.models import Candidate, PollingStation, Ward

    position_id = geo["positions"]["president"]
    with app.app_context():
        candidate = Candidate(position_id=position_id, full_name="Candidate A", normalized_name="CANDIDATE A")
        db.session.add(candidate)
        db.session.flush()

        target_ward = db.session.get(PollingStation, geo["station_id"]).ward
        other_ward = Ward(constituency_id=target_ward.constituency_id, name="Other Ward")
        db.session.add(other_ward)
        db.session.flush()

        same_ward_station = PollingStation(ward_id=target_ward.id, iebc_code="WM777", name="Same Ward Station")
        other_ward_station = PollingStation(ward_id=other_ward.id, iebc_code="WM888", name="Other Ward Station")
        db.session.add_all([same_ward_station, other_ward_station])
        db.session.commit()
        candidate_id = str(candidate.id)
        same_ward_station_id, other_ward_station_id = str(same_ward_station.id), str(other_ward_station.id)
        target_ward_name = target_ward.name

    now = datetime.now(timezone.utc)
    _seed_approved(app, position_id, candidate_id, geo["station_id"], now, 40, "grp1")
    _seed_approved(app, position_id, candidate_id, same_ward_station_id, now, 60, "grp2")
    _seed_approved(app, position_id, candidate_id, other_ward_station_id, now, 25, "grp3")

    resp = client.get(f"/api/tally/by_group?position_id={position_id}&level=ward")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["level"] == "ward"
    by_name = {g["group_name"]: g for g in body["groups"]}
    assert by_name[target_ward_name]["votes"][candidate_id] == 100  # 40 + 60, same ward
    assert by_name["Other Ward"]["votes"][candidate_id] == 25
