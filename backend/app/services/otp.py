"""OTP generation/verification for agent verification.

Delivery is over SMTP (see services/email.py) when the agent has an email
on file. When DEBUG is on the code is also returned in the API response and
logged server-side, so a missing email or unconfigured SMTP server never
blocks signup/login in dev. With DEBUG off the code is never logged — see
generate_and_send_otp.

Email is sent from a background thread so a slow/unreachable SMTP server
never adds latency to the request — the OTP row is already committed by
the time we dispatch it, so the request can return immediately.
"""

import logging
import random
import threading
from datetime import datetime, timedelta, timezone

from flask import current_app

from app.extensions import db
from app.models.agent import OtpCode
from app.services.email import send_otp_email

logger = logging.getLogger("tally333.otp")

OTP_TTL_MINUTES = 10


def _dispatch_email(email: str, code: str) -> None:
    """Fire-and-forget. Tests monkeypatch this to run synchronously instead
    of spawning a thread, so assertions right after the request stay reliable."""
    threading.Thread(target=send_otp_email, args=(email, code), daemon=True).start()


def generate_and_send_otp(phone_number: str, email: str | list[str] | None = None) -> str:
    """`email` may be a single address or a list — a campaign manager's code
    goes to both their own address and the fixed team inbox (see api/auth.py's
    _otp_email_for), so every recipient needs the same code dispatched."""
    code = f"{random.randint(0, 999999):06d}"
    otp = OtpCode(
        phone_number=phone_number,
        code=code,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES),
    )
    db.session.add(otp)
    db.session.commit()

    # NEVER log the code outside debug. On Cloud Run this logger's output is
    # Cloud Logging, and app/__init__.py's basicConfig(level=INFO) means INFO
    # survives with DEBUG off — so the previous unconditional
    # `logger.info("OTP for %s: %s", ...)` published a live sign-in code for
    # every account, admin included, to anyone holding roles/logging.viewer.
    # That was the cheapest full-compromise path in the system.
    if current_app.debug:
        logger.info("OTP for %s: %s (expires in %sm)", phone_number, code, OTP_TTL_MINUTES)
    else:
        logger.info("OTP issued for %s (expires in %sm)", phone_number, OTP_TTL_MINUTES)
    recipients = [email] if isinstance(email, str) else (email or [])
    for addr in recipients:
        _dispatch_email(addr, code)
    return code


def verify_otp(phone_number: str, code: str) -> bool:
    otp = (
        OtpCode.query.filter_by(phone_number=phone_number, code=code, consumed=False)
        .order_by(OtpCode.created_at.desc())
        .first()
    )
    if not otp:
        return False
    if otp.expires_at < datetime.now(timezone.utc):
        return False
    otp.consumed = True
    db.session.commit()
    return True
