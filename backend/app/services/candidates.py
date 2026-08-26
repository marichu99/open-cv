"""Candidates are discovered from Claude Vision extraction, not pre-seeded —
the system doesn't know who's running until an agent's first form is read.

Known limitation, deliberately not solved here: no fuzzy name matching. If
the same candidate is read as "ODINGA RAILA" on one form and "RAILA ODINGA"
on another, they become two separate Candidate rows. Revisit if that turns
out to matter in practice — don't build NLP name-matching preemptively.
"""

import re

from app.extensions import db
from app.models import Candidate, ElectivePosition


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().upper())


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
    candidate = Candidate.query.filter_by(
        position_id=position.id,
        county_id=county_id,
        constituency_id=constituency_id,
        ward_id=ward_id,
        normalized_name=normalized,
    ).first()
    if candidate:
        return candidate

    candidate = Candidate(
        position_id=position.id,
        county_id=county_id,
        constituency_id=constituency_id,
        ward_id=ward_id,
        full_name=full_name.strip(),
        normalized_name=normalized,
        party=party,
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
