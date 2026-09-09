"""Input coercion for figures that end up summed into the live tally.

The DB CHECK constraints from migration c3f1a72b9d84 are the backstop; these
helpers exist so a bad value comes back as a clean 400 naming the field
rather than an IntegrityError surfacing as a 500.
"""

from app.models.submission import MAX_VOTES_PER_FIELD
from app.utils.errors import ApiError


def parse_vote_count(value, field_label: str) -> int | None:
    """Coerces a caller-supplied vote figure to a bounded non-negative int.

    `None` is passed through — for `votes_corrected` that legitimately means
    "no correction, fall back to votes_detected" (see
    VoteRecord.effective_votes).

    Rejects bools explicitly: `isinstance(True, int)` is True in Python, so
    a JSON `true` would otherwise sail through as 1 vote.
    """
    if value is None:
        return None

    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError(f"{field_label} must be a whole number")

    if value < 0:
        # Negative figures don't just fail validation, they actively
        # SUBTRACT from a candidate's national total via
        # tally_service.EFFECTIVE_VOTES — worth its own message.
        raise ApiError(f"{field_label} cannot be negative")

    if value > MAX_VOTES_PER_FIELD:
        raise ApiError(f"{field_label} exceeds the maximum of {MAX_VOTES_PER_FIELD:,} for a single station form")

    return value
