"""Demo account seeding.

Geography and elective positions come from `flask import-geography` (see
import_geography.py), not here. This command only creates demo login
accounts — no fake candidates or submissions. Analytics/dashboards start
genuinely blank; a candidate only exists once a real form has been
extracted, and the tally only moves once a real submission is approved.

Usage:
    flask --app wsgi seed
"""

from datetime import datetime, timezone

import click
from flask.cli import with_appcontext

from app.extensions import db
from app.models import Agent

# Every account signs in with a one-time code emailed to it — so unlike a
# password, `email` here isn't optional bookkeeping, it's the only way any
# of these demo accounts can actually receive a login code. Campaign
# managers additionally always get their code at the fixed inbox in
# api/auth.py too, on top of their own address below.
DEMO_ACCOUNTS = [
    {"full_name": "County Admin", "phone_number": "+254700000001", "email": "admin@example.com", "role": "admin"},
    {"full_name": "Constituency Coordinator", "phone_number": "+254700000002", "email": "coordinator@example.com", "role": "coordinator"},
    {"full_name": "Campaign Manager", "phone_number": "+254700000003", "email": "campaign.manager@example.com", "role": "campaign_manager"},
    {"full_name": "Demo Agent", "phone_number": "+254711111111", "email": "demo.agent@example.com", "role": "agent", "verified": True},
]


def _seed_accounts():
    for acc in DEMO_ACCOUNTS:
        agent = Agent(
            full_name=acc["full_name"],
            phone_number=acc["phone_number"],
            email=acc.get("email"),
            role=acc["role"],
        )
        if acc.get("verified"):
            agent.phone_verified_at = datetime.now(timezone.utc)
        db.session.add(agent)
    db.session.commit()


@click.command("seed")
@with_appcontext
def seed_command():
    if Agent.query.filter_by(phone_number="+254700000001").first():
        click.echo("Demo accounts already exist — skipping.")
        return

    click.echo("Seeding demo accounts...")
    _seed_accounts()

    click.echo("Done. Run `flask --app wsgi import-geography` too if you haven't yet.")
    click.echo("All accounts sign in with a one-time code (POST /api/auth/agents/otp/request, then /api/auth/agents/verify):")
    click.echo("  admin             +254700000001 — code emailed to admin@example.com")
    click.echo("  coordinator       +254700000002 — code emailed to coordinator@example.com")
    click.echo("  campaign manager  +254700000003 — code emailed to campaign.manager@example.com and the fixed campaign-manager inbox")
    click.echo("  demo agent        +254711111111 — code emailed to demo.agent@example.com (no position/station assigned)")


def register_cli(app):
    app.cli.add_command(seed_command)
