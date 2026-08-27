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
from app.models import Candidate, ElectivePosition


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
