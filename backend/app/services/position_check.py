"""Cross-checks the elective position/race Claude Vision reads off the form
itself against the position the agent selected in the upload dropdown — an
agent assigned to more than one position (e.g. President and Woman
Representative) can select the wrong one for a given photo, and nothing else
in the pipeline would catch that: candidates get created/matched purely
against whatever position_id was declared, so a real Woman Rep aspirant
would silently become a "presidential candidate" with real vote totals.
"""

from app.models.candidate import POSITION_LABELS


def position_mismatch(detected_position: str | None, position) -> str | None:
    """None means either everything matches, or the extraction backend
    doesn't read the position off the form at all (`detected_position` is
    None) — in which case there's nothing to cross-check against, mirroring
    location_mismatches' handling of a None detected_location."""
    if not detected_position or detected_position == position.name:
        return None

    detected_label = POSITION_LABELS.get(detected_position, detected_position)
    declared_label = POSITION_LABELS.get(position.name, position.name)
    return (
        f'This looks like a {detected_label} form, but you selected {declared_label} — '
        "please retake it after selecting the correct position."
    )
