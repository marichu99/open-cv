"""Cross-checks the County/Constituency/Ward/Polling Station header printed
on a form against what the agent selected for the upload — an agent can
easily upload the right photo to the wrong station in the dropdown (or vice
versa), and nothing else in the pipeline would catch that: extraction reads
whatever's in the photo regardless of what was declared.
"""

import re


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
    name's words are shared" for names that partially overlap without one
    being a strict subset of the other."""
    d, a = _normalize(detected), _normalize(actual)
    if not d or not a:
        return True
    d_tokens, a_tokens = set(d.split()), set(a.split())
    if d_tokens <= a_tokens or a_tokens <= d_tokens:
        return True
    overlap = d_tokens & a_tokens
    shorter = min(len(d_tokens), len(a_tokens))
    return shorter > 0 and len(overlap) / shorter >= 0.5


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
