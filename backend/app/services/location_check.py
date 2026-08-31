"""Cross-checks the County/Constituency/Ward/Polling Station header printed
on a form against what the agent selected for the upload — an agent can
easily upload the right photo to the wrong station in the dropdown (or vice
versa), and nothing else in the pipeline would catch that: extraction reads
whatever's in the photo regardless of what was declared.
"""

import re


#: Institution-type/boilerplate words that recur across thousands of real
#: Kenyan polling station names — sharing only these between a detected
#: header and a stored name isn't a meaningful signal that they're the same
#: place ("Ensakia Primary School" and "Nyagacho Primary School" share
#: "PRIMARY SCHOOL" but are two different, real stations in different
#: wards). Used only to decide whether a *partial* overlap counts as a
#: match — a name that's a strict subset/superset of the other still
#: matches regardless (see _matches below), so this never blocks the
#: verbose-header case the leniency exists for in the first place.
_GENERIC_TOKENS = {
    "PRIMARY", "SECONDARY", "SCHOOL", "POLLING", "STATION", "CENTRE", "CENTER",
    "TBC", "DEB", "DOK", "POLYTECHNIC", "ACADEMY", "COLLEGE", "INSTITUTE",
    "HALL", "CHIEFS", "CAMP", "MARKET", "GROUND", "GROUNDS", "DISPENSARY",
    "CHURCH", "MOSQUE", "YOUTH", "TRAINING", "TECHNICAL", "MIXED", "DAY",
    "BOARDING", "SOCIAL", "COMPLEX", "OF", "AND", "THE",
}


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"[^A-Z0-9 ]", " ", text.upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def _matches(detected: str, actual: str) -> bool:
    """Lenient by design: real form headers are verbose and inconsistently
    formatted ("GETARE TBC (TEA BUYING CENTRE) POLLING STATION 1 of 2" vs a
    shorter stored name), so this isn't exact-string matching — it's token
    containment either way, falling back to "at least half the shorter
    name's *significant* words are shared" for names that partially overlap
    without one being a strict subset of the other. "Significant" excludes
    pure-digit tokens (a stream indicator like the "1"/"2" in "... 1 of 2"
    never identifies a place) and _GENERIC_TOKENS — without that exclusion,
    two entirely different short station names sharing only generic words
    ("Primary School") could cross the 50% threshold on boilerplate alone."""
    d, a = _normalize(detected), _normalize(actual)
    if not d or not a:
        return True
    d_tokens = {t for t in d.split() if not t.isdigit()}
    a_tokens = {t for t in a.split() if not t.isdigit()}
    if not d_tokens or not a_tokens:
        return True
    if d_tokens <= a_tokens or a_tokens <= d_tokens:
        return True

    d_significant = d_tokens - _GENERIC_TOKENS
    a_significant = a_tokens - _GENERIC_TOKENS
    shorter_significant = min(len(d_significant), len(a_significant))
    if shorter_significant == 0:
        # Both names are entirely generic words (rare) — nothing meaningful
        # to require overlap of, so fall back to the plain ratio rather
        # than refusing to ever match.
        overlap = d_tokens & a_tokens
        shorter = min(len(d_tokens), len(a_tokens))
        return shorter > 0 and len(overlap) / shorter >= 0.5

    significant_overlap = (d_tokens & a_tokens) - _GENERIC_TOKENS
    return len(significant_overlap) / shorter_significant >= 0.5


def location_mismatches(detected_location, station) -> list[str]:
    """Returns one human-readable description per header field that clearly
    doesn't match the selected station's actual geography. An empty list
    means either everything matches, or the extraction backend doesn't read
    the header at all (`detected_location` is None) — in which case there's
    nothing to cross-check against, so nothing is flagged."""
    if detected_location is None:
        return []

    ward = station.ward
    constituency = ward.constituency
    county = constituency.county

    fields = [
        ("county", detected_location.county, county.name),
        ("constituency", detected_location.constituency, constituency.name),
        ("ward", detected_location.ward, ward.name),
        ("polling station", detected_location.polling_station, station.name),
    ]
    return [
        f'{label} (form says "{detected.strip()}", you selected "{actual}")'
        for label, detected, actual in fields
        if detected and not _matches(detected, actual)
    ]
