import re


def normalize_phone_number(raw: str) -> str:
    """Normalize a Kenyan phone number to E.164 (+254XXXXXXXXX) so the same
    number typed as 0712345678, 712345678, 254712345678, or +254712345678
    always resolves to the same account — signup and sign-in used to do a
    raw string match, so typing the number in a different format than it was
    registered with looked like "no account exists"."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("254"):
        digits = digits[3:]
    elif digits.startswith("0"):
        digits = digits[1:]
    return f"+254{digits}" if digits else ""
