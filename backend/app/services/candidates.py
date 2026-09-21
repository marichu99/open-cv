"""Candidates are matched against whatever's already on record for a
position/scope — either seeded ahead of time by a campaign manager (see
`POST /api/candidates`) or discovered from the first form Claude Vision
reads. Either way, a name read slightly differently on a later form (a
middle name present on one scan and not another, word order swapped)
should still land on the *same* candidate rather than fragmenting their
vote count across rows — see `_find_match`.
"""

import re

from app.extensions import db
from app.models import Agent, Candidate, County, Constituency, ElectivePosition, Ward


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().upper())


def _find_match(normalized: str, existing: list[Candidate]) -> Candidate | None:
    tokens = set(normalized.split())
    if not tokens:
        return None
    for candidate in existing:
        existing_tokens = set(candidate.normalized_name.split())
        # A name is the same person read more/less fully — e.g. "ODINGA
        # RAILA" vs "ODINGA RAILA AMOLO" — when one name's tokens are
        # wholly contained in the other's (this also catches word-order
        # swaps like "RAILA ODINGA", since token sets ignore order).
        if tokens <= existing_tokens or existing_tokens <= tokens:
            return candidate
    return None


def get_or_create_candidate(
    position: ElectivePosition,
    full_name: str,
    party: str | None = None,
    *,
    county_id=None,
    constituency_id=None,
    ward_id=None,
) -> Candidate:
    normalized = normalize_name(full_name)
    scope = dict(position_id=position.id, county_id=county_id, constituency_id=constituency_id, ward_id=ward_id)

    candidate = Candidate.query.filter_by(normalized_name=normalized, **scope).first()
    if candidate:
        return candidate

    match = _find_match(normalized, Candidate.query.filter_by(**scope).all())
    if match:
        return match

    candidate = Candidate(
        full_name=full_name.strip(),
        normalized_name=normalized,
        party=party,
        **scope,
    )
    db.session.add(candidate)
    db.session.flush()
    return candidate


def geo_scope_for_position(position: ElectivePosition, station) -> dict:
    """Resolves the (county_id, constituency_id, ward_id) kwargs for
    get_or_create_candidate given a position's level and a polling station
    (via station.ward.constituency.county)."""
    ward = station.ward
    constituency = ward.constituency
    if position.level == "ward":
        return {"ward_id": ward.id}
    if position.level == "constituency":
        return {"constituency_id": constituency.id}
    if position.level == "county":
        return {"county_id": constituency.county_id}
    return {}  # national


def inherited_assignment(agent: Agent) -> dict | None:
    """What a field agent's campaign-manager -> aspirant chain already
    implies about their race and geography, before a campaign manager has
    assigned anything explicitly (see api/agents.py's assign_station and
    api/auth.py's register_agent, the two callers). Walks the relational
    chain each signup already declares — Agent.assigned_by (the campaign
    manager) -> Agent.aspirant_id -> Agent.candidate_id -> the candidate's
    own position/geo scope — rather than copying it onto the agent row, so
    it can never drift out of sync if the aspirant's own candidacy is ever
    corrected.

    None when the agent has no campaign manager yet, or that campaign
    manager hasn't linked to an aspirant with a resolvable candidacy.
    `county`/`constituency`/`ward` are each None unless the aspirant's own
    position.level implies that level — a national position (e.g.
    President) implies no geography to narrow at all, only the position
    itself."""
    campaign_manager = db.session.get(Agent, agent.assigned_by) if agent.assigned_by else None
    aspirant = campaign_manager.aspirant if campaign_manager else None
    candidate = aspirant.candidate if aspirant else None
    if not candidate:
        return None

    position = db.session.get(ElectivePosition, candidate.position_id)
    ward = db.session.get(Ward, candidate.ward_id) if candidate.ward_id else None
    constituency = (
        db.session.get(Constituency, candidate.constituency_id)
        if candidate.constituency_id
        else (db.session.get(Constituency, ward.constituency_id) if ward else None)
    )
    county = (
        db.session.get(County, candidate.county_id)
        if candidate.county_id
        else (db.session.get(County, constituency.county_id) if constituency else None)
    )
    return {
        "aspirant_name": aspirant.full_name,
        "position": position.to_dict() if position else None,
        "county": county.to_dict() if county else None,
        "constituency": constituency.to_dict() if constituency else None,
        "ward": ward.to_dict() if ward else None,
    }
