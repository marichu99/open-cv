"""National geography + elective-position import.

Geography source: seed_data/kenya_geography.json — a static, one-time export
of Kenya's county > constituency > ward > polling station hierarchy (47
counties, 290 constituencies, ~1,450 wards, ~24.6k polling stations), MIT
licensed, sourced from IEBC/public government resources via
github.com/stevehoober254/kenya-county-data. No official IEBC station codes
in that source — only names — so PollingStation.iebc_code is null except
where backfilled below.

Nyamira backfill: the sample Form 34A PDFs this project was built against
(F34A-046-270-1346-001-01.PDF etc — county-constituency-ward-station-stream)
carry real IEBC codes in their filenames. If that PDF directory is present on
this machine, backfill real codes for Nyamira's ~332 stations by matching
ward+station name; everywhere else iebc_code stays null. This step is
optional and silently skipped if the directory doesn't exist — it's a
nice-to-have for the one county we have real source documents for, not a
requirement for the import to succeed elsewhere.

Usage:
    flask --app wsgi import-geography
"""

import json
import os

import click
from flask.cli import with_appcontext

from app.extensions import db
from app.models import County, Constituency, Ward, PollingStation, ElectivePosition

GEOGRAPHY_JSON = os.path.join(os.path.dirname(__file__), "seed_data", "kenya_geography.json")

# Sample PDFs are outside the repo (a local download), so this path is best-effort.
NYAMIRA_PDF_DIR = "/home/mabera/Downloads/8P1L1_Nyamira_All/A_Series"

POSITIONS = [
    {"name": "president", "form_series": "34", "level": "national"},
    {"name": "member_of_parliament", "form_series": "35", "level": "constituency"},
    {"name": "mca", "form_series": "36", "level": "ward"},
    {"name": "governor", "form_series": "37", "level": "county"},
    {"name": "senator", "form_series": "38", "level": "county"},
    {"name": "woman_representative", "form_series": "39", "level": "county"},
]


def _import_geography():
    with open(GEOGRAPHY_JSON) as fh:
        counties = json.load(fh)

    for county_data in counties:
        county = County(name=county_data["name"])
        db.session.add(county)
        db.session.flush()
        for const_data in county_data["constituencies"]:
            constituency = Constituency(county_id=county.id, name=const_data["name"])
            db.session.add(constituency)
            db.session.flush()
            for ward_data in const_data["wards"]:
                ward = Ward(constituency_id=constituency.id, name=ward_data["name"])
                db.session.add(ward)
                db.session.flush()
                for station_data in ward_data["pollingStations"]:
                    db.session.add(PollingStation(ward_id=ward.id, name=station_data["name"]))
    db.session.commit()


def _backfill_nyamira_codes():
    """NOT IMPLEMENTED YET — deliberately. The PDF filenames encode numeric
    county/constituency/ward/station codes (e.g. 046-270-1346-001), but not
    the ward/station *names* needed to match them against the imported
    geography rows — that requires reading each form's printed header
    (name of polling station / ward / constituency), which means running
    every one of the ~332 Nyamira PDFs through OCR/Claude Vision just to
    build a code lookup table. That's real, billable work worth doing
    deliberately, not as a silent side effect of a geography import — so
    this is a documented no-op for now. iebc_code stays null for all of
    Nyamira like everywhere else until this is built."""
    if not os.path.isdir(NYAMIRA_PDF_DIR):
        click.echo(f"  (skipping — {NYAMIRA_PDF_DIR} not present on this machine)")
        return
    click.echo("  (skipping — code backfill needs each form's printed header read via OCR, not just its filename; see docstring)")


def _import_positions():
    for p in POSITIONS:
        if not ElectivePosition.query.filter_by(name=p["name"]).first():
            db.session.add(ElectivePosition(**p))
    db.session.commit()


@click.command("import-geography")
@with_appcontext
def import_geography_command():
    if County.query.first():
        click.echo("Geography already imported — skipping. Drop the county/constituency/ward/polling_station tables first to re-import.")
        return

    click.echo("Importing national geography (47 counties, 290 constituencies, ~1,450 wards, ~24.6k stations)...")
    _import_geography()
    click.echo("Backfilling real IEBC codes for Nyamira where possible...")
    _backfill_nyamira_codes()
    click.echo("Seeding elective positions...")
    _import_positions()
    click.echo("Done.")


def register_cli(app):
    app.cli.add_command(import_geography_command)
