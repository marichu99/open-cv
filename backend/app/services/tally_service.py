"""Live tally aggregation, scoped by elective position — each of the 6
positions has an entirely different candidate set (President is national;
Governor/Senator/Woman Rep are per-county; MP per-constituency; MCA per-ward)
so every query here takes a `position` and, for non-national positions, a
`scope_id` naming the specific county/constituency/ward being viewed.

Only station-level ("A" form) approved submissions count toward the tally —
B/C/D forms are stored for cross-validation, not summed again.
"""

from sqlalchemy import func

from app.extensions import db
from app.models import Candidate, County, Constituency, Ward, PollingStation, FormSubmission, VoteRecord
from app.models.submission import TALLIED_STATUSES

EFFECTIVE_VOTES = func.coalesce(VoteRecord.votes_corrected, VoteRecord.votes_detected)


def _scope_kwargs(position, scope_id):
    if not scope_id:
        return {}
    return {
        "county": {"county_id": scope_id},
        "constituency": {"constituency_id": scope_id},
        "ward": {"ward_id": scope_id},
    }.get(position.level, {})


def _station_query_for_scope(position, scope_id):
    """PollingStation query restricted to the geography a position/scope covers."""
    q = PollingStation.query
    if position.level == "ward":
        if scope_id:
            q = q.filter(PollingStation.ward_id == scope_id)
    elif position.level == "constituency":
        q = q.join(Ward, Ward.id == PollingStation.ward_id)
        if scope_id:
            q = q.filter(Ward.constituency_id == scope_id)
    elif position.level == "county":
        q = q.join(Ward, Ward.id == PollingStation.ward_id).join(Constituency, Constituency.id == Ward.constituency_id)
        if scope_id:
            q = q.filter(Constituency.county_id == scope_id)
    # national (president): no restriction — every station counts
    return q


def stations_progress(position, scope_id=None):
    total = _station_query_for_scope(position, scope_id).count()
    form_type = f"{position.form_series}A"
    reported_q = (
        db.session.query(func.count(func.distinct(FormSubmission.station_id)))
        .filter(FormSubmission.position_id == position.id)
        .filter(FormSubmission.form_type == form_type)
        .filter(FormSubmission.status.in_(TALLIED_STATUSES))
    )
    if scope_id and position.level != "national":
        station_ids = _station_query_for_scope(position, scope_id).with_entities(PollingStation.id)
        reported_q = reported_q.filter(FormSubmission.station_id.in_(station_ids))
    reported = reported_q.scalar() or 0
    return {"reported": reported, "total": total}


def candidate_totals(position, scope_id=None):
    """Vote totals per candidate for this position/scope. `scope_id` is
    required for county/constituency/ward-level positions (there's no
    single sensible answer to "how many votes did this Governor candidate
    get" without naming the county) — omitted for `national` (President)."""
    form_type = f"{position.form_series}A"
    candidates = Candidate.query.filter_by(position_id=position.id, **_scope_kwargs(position, scope_id)).all()

    totals_query = (
        db.session.query(VoteRecord.candidate_id, func.sum(EFFECTIVE_VOTES))
        .join(FormSubmission, VoteRecord.submission_id == FormSubmission.id)
        .filter(FormSubmission.position_id == position.id)
        .filter(FormSubmission.form_type == form_type)
        .filter(FormSubmission.status.in_(TALLIED_STATUSES))
    )
    if scope_id and position.level != "national":
        station_ids = _station_query_for_scope(position, scope_id).with_entities(PollingStation.id)
        totals_query = totals_query.filter(FormSubmission.station_id.in_(station_ids))
    totals = dict(totals_query.group_by(VoteRecord.candidate_id).all())

    results = [
        {
            "candidate_id": str(c.id),
            "full_name": c.full_name,
            "party": c.party,
            "votes": int(totals.get(c.id, 0)),
        }
        for c in candidates
    ]
    progress = stations_progress(position, scope_id)
    return {
        "candidates": sorted(results, key=lambda r: r["votes"], reverse=True),
        "stations_reported": progress["reported"],
        "stations_total": progress["total"],
    }


#: Coarsest-to-finest. `func.date_trunc` takes these as a bound parameter, so
#: this allowlist is about giving a clean error, not preventing injection.
GRANULARITIES = ("day", "hour", "minute", "second")


def _auto_granularity(min_ts, max_ts) -> str:
    """Picks a bucket size that keeps the chart legible instead of either a
    flat line (too coarse for the actual reporting window) or a bucket per
    point (too fine to read) — e.g. a burst of submissions over 2 minutes of
    testing shouldn't render as one hourly dot, and a real multi-day count
    shouldn't render as thousands of by-the-second dots."""
    if not min_ts or not max_ts:
        return "hour"
    span = (max_ts - min_ts).total_seconds()
    if span <= 5 * 60:
        return "second"
    if span <= 3 * 60 * 60:
        return "minute"
    if span <= 3 * 24 * 60 * 60:
        return "hour"
    return "day"


def timeseries(position, scope_id=None, granularity: str | None = None):
    form_type = f"{position.form_series}A"
    candidates = Candidate.query.filter_by(position_id=position.id, **_scope_kwargs(position, scope_id)).all()

    filters = [
        FormSubmission.position_id == position.id,
        FormSubmission.form_type == form_type,
        FormSubmission.status.in_(TALLIED_STATUSES),
        FormSubmission.finalized_at.isnot(None),
    ]
    if scope_id and position.level != "national":
        station_ids = _station_query_for_scope(position, scope_id).with_entities(PollingStation.id)
        filters.append(FormSubmission.station_id.in_(station_ids))

    if granularity not in GRANULARITIES:
        min_ts, max_ts = db.session.query(
            func.min(FormSubmission.finalized_at), func.max(FormSubmission.finalized_at)
        ).filter(*filters).one()
        granularity = _auto_granularity(min_ts, max_ts)

    bucket = func.date_trunc(granularity, FormSubmission.finalized_at)
    rows = (
        db.session.query(bucket.label("bucket"), VoteRecord.candidate_id, func.sum(EFFECTIVE_VOTES))
        .join(FormSubmission, VoteRecord.submission_id == FormSubmission.id)
        .filter(*filters)
        .group_by("bucket", VoteRecord.candidate_id)
        .order_by("bucket")
        .all()
    )

    buckets = sorted({r.bucket for r in rows})
    running = {c.id: 0 for c in candidates}
    per_bucket = {b: {c.id: 0 for c in candidates} for b in buckets}
    for bucket_ts, candidate_id, total in rows:
        if candidate_id in per_bucket[bucket_ts]:
            per_bucket[bucket_ts][candidate_id] = int(total)

    series = []
    for b in buckets:
        for candidate_id, delta in per_bucket[b].items():
            running[candidate_id] += delta
        series.append({"timestamp": b.isoformat(), "cumulative": {str(cid): total for cid, total in running.items()}})
    return {
        "candidates": [{"candidate_id": str(c.id), "full_name": c.full_name} for c in candidates],
        "series": series,
        "granularity": granularity,
    }


def votes_by_station(position, scope_id=None):
    """Per-station breakdown of what's currently counting toward the tally —
    one row per reporting station, most recently finalized first, with each
    candidate's vote count so it reads as a live feed of how the total is
    being built up station by station."""
    form_type = f"{position.form_series}A"
    candidates = Candidate.query.filter_by(position_id=position.id, **_scope_kwargs(position, scope_id)).all()

    q = (
        FormSubmission.query.filter_by(position_id=position.id, form_type=form_type)
        .filter(FormSubmission.status.in_(TALLIED_STATUSES))
    )
    if scope_id and position.level != "national":
        station_ids = _station_query_for_scope(position, scope_id).with_entities(PollingStation.id)
        q = q.filter(FormSubmission.station_id.in_(station_ids))
    submissions = q.order_by(FormSubmission.finalized_at.desc().nullslast()).limit(500).all()

    stations = [
        {
            "station_id": str(s.station_id),
            "station_name": s.station.name,
            "stream_number": s.stream_number,
            "reported_at": s.finalized_at.isoformat() if s.finalized_at else None,
            "votes": {str(vr.candidate_id): vr.effective_votes for vr in s.vote_records},
            "total_votes_cast": s.total_votes_cast,
            "rejected_ballots": s.rejected_ballots,
        }
        for s in submissions
    ]
    return {
        "candidates": [{"candidate_id": str(c.id), "full_name": c.full_name} for c in candidates],
        "stations": stations,
    }


def sub_regions(position):
    """Pickable scopes for this position's dashboard view — counties for
    county-level races, constituencies for constituency-level, wards for
    ward-level. National positions (President) have no scope to pick."""
    if position.level == "county":
        return [c.to_dict() for c in County.query.order_by(County.name)]
    if position.level == "constituency":
        return [c.to_dict() for c in Constituency.query.order_by(Constituency.name)]
    if position.level == "ward":
        return [w.to_dict() for w in Ward.query.order_by(Ward.name)]
    return []


def positions_with_data():
    """Positions that have at least one candidate discovered so far (i.e.
    at least one real submission has been extracted) — drives the
    dashboard's position selector so it never shows an all-blank race."""
    position_ids = [row[0] for row in db.session.query(Candidate.position_id).distinct().all()]
    return position_ids


#: Coarsest-to-finest — mirrors the geography hierarchy, "station" appended
#: since it's the finest level a submission ever reports at.
GEO_LEVELS = ("county", "constituency", "ward", "station")


def valid_groupings(position) -> list[str]:
    """Grouping levels that actually partition this position's current
    scope into more than one bucket. Anything at or coarser than the
    position's own scope level always collapses to a single row within the
    current selection — e.g. a Governor race is already scoped to one
    county, so grouping it "by county" would just repeat the Totals card,
    and MCA (already ward-scoped) has nothing coarser than station left to
    group by at all."""
    if position.level == "national":
        return list(GEO_LEVELS)
    start = GEO_LEVELS.index(position.level) + 1
    return list(GEO_LEVELS[start:])


def votes_by_group(position, scope_id, level: str):
    """Vote totals per candidate, grouped by county/constituency/ward —
    aggregates every reporting station within each group. Only groups that
    have at least one counted submission are returned (an all-zero row for
    every one of 47 counties before results start coming in isn't useful),
    ranked by total votes so it reads like a mini leaderboard of reporting
    activity."""
    if level == "station":
        return votes_by_station(position, scope_id)
    if level not in GEO_LEVELS:
        raise ValueError(f"Unknown grouping level: {level!r}")

    form_type = f"{position.form_series}A"
    candidates = Candidate.query.filter_by(position_id=position.id, **_scope_kwargs(position, scope_id)).all()

    bucket_id, bucket_name = {
        "ward": (Ward.id, Ward.name),
        "constituency": (Constituency.id, Constituency.name),
        "county": (County.id, County.name),
    }[level]

    query = (
        db.session.query(bucket_id, bucket_name, VoteRecord.candidate_id, func.sum(EFFECTIVE_VOTES))
        .select_from(FormSubmission)
        .join(VoteRecord, VoteRecord.submission_id == FormSubmission.id)
        .join(PollingStation, PollingStation.id == FormSubmission.station_id)
        .join(Ward, Ward.id == PollingStation.ward_id)
        .join(Constituency, Constituency.id == Ward.constituency_id)
        .join(County, County.id == Constituency.county_id)
        .filter(FormSubmission.position_id == position.id)
        .filter(FormSubmission.form_type == form_type)
        .filter(FormSubmission.status.in_(TALLIED_STATUSES))
    )
    if scope_id and position.level != "national":
        station_ids = _station_query_for_scope(position, scope_id).with_entities(PollingStation.id)
        query = query.filter(FormSubmission.station_id.in_(station_ids))

    rows = query.group_by(bucket_id, bucket_name, VoteRecord.candidate_id).all()

    groups: dict[str, dict] = {}
    for gid, gname, candidate_id, total in rows:
        group = groups.setdefault(str(gid), {"group_id": str(gid), "group_name": gname, "votes": {}})
        group["votes"][str(candidate_id)] = int(total)

    ordered = sorted(groups.values(), key=lambda g: sum(g["votes"].values()), reverse=True)
    return {
        "candidates": [{"candidate_id": str(c.id), "full_name": c.full_name} for c in candidates],
        "level": level,
        "groups": ordered,
    }
