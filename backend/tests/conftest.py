import io

import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import County, Constituency, Ward, PollingStation, ElectivePosition

POSITIONS = [
    {"name": "president", "form_series": "34", "level": "national"},
    {"name": "member_of_parliament", "form_series": "35", "level": "constituency"},
    {"name": "mca", "form_series": "36", "level": "ward"},
    {"name": "governor", "form_series": "37", "level": "county"},
    {"name": "senator", "form_series": "38", "level": "county"},
    {"name": "woman_representative", "form_series": "39", "level": "county"},
]


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def geo(app):
    with app.app_context():
        county = County(name="Nyamira")
        db.session.add(county)
        db.session.flush()
        constituency = Constituency(county_id=county.id, name="West Mugirango")
        db.session.add(constituency)
        db.session.flush()
        ward = Ward(constituency_id=constituency.id, name="Nyansiongo")
        db.session.add(ward)
        db.session.flush()
        station = PollingStation(ward_id=ward.id, iebc_code="WM101", name="Nyansiongo Pri Stream 1")
        db.session.add(station)
        db.session.flush()

        positions = {}
        for p in POSITIONS:
            pos = ElectivePosition(**p)
            db.session.add(pos)
            db.session.flush()
            positions[p["name"]] = str(pos.id)

        db.session.commit()
        return {
            "county_id": str(county.id),
            "constituency_id": str(constituency.id),
            "ward_id": str(ward.id),
            "station_id": str(station.id),
            "positions": positions,
        }


def fake_image_bytes():
    return io.BytesIO(b"fake-jpeg-bytes-for-testing")


def fake_pdf_bytes():
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    # A single line of text renders as a near-blank page — draw enough of a
    # table-like grid that this actually looks like a filled-in form (the
    # blank-photo pre-filter would otherwise reject it, correctly, since a
    # one-liner really is what it's checking for).
    for i in range(10):
        y = 72 + i * 20
        page.draw_line((72, y), (500, y))
        page.insert_text((80, y - 4), f"Row {i}: Test Form 34A candidate line")
    buf = doc.tobytes()
    doc.close()
    return io.BytesIO(buf)
