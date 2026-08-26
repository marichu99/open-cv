"""OTP delivery over SMTP. Adapted from the same pattern used in the
Leviathan project (backend/app/services/email.py) — plain smtplib, no extra
dependency.

Configure via env vars (see .env.example): SMTP_HOST, SMTP_PORT, SMTP_USER
(or SMTP_USERNAME), SMTP_PASSWORD, EMAIL_FROM. If sending fails and we're
not in production, the error is logged and swallowed rather than raised —
the OTP is always logged server-side too (services/otp.py), so a broken
SMTP config never blocks signup/login in dev.
"""

import logging
import os
import smtplib
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger("tally333.email")


def send_otp_email(to_email: str, otp_code: str) -> None:
    try:
        _send_via_smtp(to_email, otp_code)
    except (socket.gaierror, ConnectionError, TimeoutError, OSError, smtplib.SMTPException):
        if os.environ.get("FLASK_ENV", "development") != "production":
            logger.warning(
                "Could not send OTP email to %s (SMTP unreachable/unconfigured) — code already logged above",
                to_email,
            )
            return
        raise


def _build_content(otp_code: str):
    subject = "Your Tally333 verification code"
    plain = (
        f"Your verification code is: {otp_code}\n\n"
        "This code expires in 10 minutes. Do not share it with anyone."
    )
    html = f"""
    <div style="font-family:sans-serif;max-width:420px;margin:0 auto;padding:2rem;">
      <h2 style="margin-bottom:0.5rem;">Verify your account</h2>
      <p style="color:#555;">Enter this code on the Tally333 sign-up page:</p>
      <div style="font-size:2.25rem;font-weight:700;letter-spacing:0.6rem;
                  text-align:center;padding:1.25rem;background:#f3f3f3;
                  border-radius:10px;margin:1.5rem 0;">
        {otp_code}
      </div>
      <p style="color:#777;font-size:0.875rem;">
        This code expires in <strong>10 minutes</strong>.
        Do not share it with anyone.
      </p>
    </div>
    """
    return subject, plain, html


def _send_via_smtp(to_email: str, otp_code: str) -> None:
    subject, plain, html = _build_content(otp_code)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = os.environ.get("EMAIL_FROM") or os.environ.get("SMTP_USER", "noreply@tally333.local")
    msg["To"] = to_email
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    host = os.environ.get("SMTP_HOST", "localhost")
    port = int(os.environ.get("SMTP_PORT", 587))
    user = os.environ.get("SMTP_USER") or os.environ.get("SMTP_USERNAME", "")
    password = os.environ.get("SMTP_PASSWORD", "")

    logger.info("Sending OTP via SMTP to %s (host=%s port=%s user=%s)", to_email, host, port, user)

    with smtplib.SMTP(host, port, timeout=10) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        if user and password:
            server.login(user, password)
        server.sendmail(msg["From"], [to_email], msg.as_string())
