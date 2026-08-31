from app.services.cv_pipeline import DetectedLocation
from app.services.location_check import location_mismatches


class _Station:
    def __init__(self, name, ward):
        self.name = name
        self.ward = ward


class _Ward:
    def __init__(self, name, constituency):
        self.name = name
        self.constituency = constituency


class _Constituency:
    def __init__(self, name, county):
        self.name = name
        self.county = county


class _County:
    def __init__(self, name):
        self.name = name


def _station(station_name="Getare Tbc Polling Station", ward="Bogichora", constituency="West Mugirango", county="Nyamira"):
    return _Station(station_name, _Ward(ward, _Constituency(constituency, _County(county))))


def test_no_mismatches_when_backend_does_not_read_location():
    assert location_mismatches(None, _station()) == []


def test_no_mismatches_when_everything_matches_exactly():
    detected = DetectedLocation(county="Nyamira", constituency="West Mugirango", ward="Bogichora",
                                 polling_station="Getare Tbc Polling Station")
    assert location_mismatches(detected, _station()) == []


def test_no_mismatch_for_verbose_form_header_vs_shorter_stored_name():
    # Real forms are much more verbose than the stored geography name.
    detected = DetectedLocation(
        county="NYAMIRA", constituency="WEST MUGIRANGO", ward="BOGICHORA",
        polling_station="GETARE TBC (TEA BUYING CENTRE) POLLING STATION 1 of 2",
    )
    assert location_mismatches(detected, _station(station_name="Getare Tbc Polling Station")) == []


def test_missing_field_on_the_form_is_not_treated_as_a_mismatch():
    detected = DetectedLocation(county="Nyamira", constituency=None, ward="Bogichora", polling_station=None)
    assert location_mismatches(detected, _station()) == []


def test_flags_a_genuinely_different_ward_and_constituency():
    detected = DetectedLocation(county="Nyamira", constituency="Borabu", ward="Kiabonyoru",
                                 polling_station="Getare Tbc Polling Station")
    mismatches = location_mismatches(detected, _station())
    assert len(mismatches) == 2
    assert any("constituency" in m for m in mismatches)
    assert any("ward" in m for m in mismatches)


def test_flags_a_genuinely_different_polling_station():
    detected = DetectedLocation(county="Nyamira", constituency="West Mugirango", ward="Bogichora",
                                 polling_station="Rigoma D.e.b Primary School")
    mismatches = location_mismatches(detected, _station(station_name="Getare Tbc Polling Station"))
    assert len(mismatches) == 1
    assert "polling station" in mismatches[0]


def test_short_names_sharing_only_generic_words_are_flagged_as_a_mismatch():
    """Real bug: "Ensakia Primary School" (selected) vs a real form header
    for "Nyagacho Primary School Polling Station 1 of 2" — these are two
    different, real stations that happen to share "Primary School" and
    nothing else. The old 50%-of-shorter-set overlap heuristic let
    boilerplate words alone cross the threshold; this must not match."""
    detected = DetectedLocation(
        county="Nyamira", constituency="West Mugirango", ward="Bogichora",
        polling_station="NYAGACHO PRIMARY SCHOOL POLLING STATION 1 of 2",
    )
    mismatches = location_mismatches(detected, _station(station_name="Ensakia Primary School"))
    assert len(mismatches) == 1
    assert "polling station" in mismatches[0]


def test_short_names_still_match_when_the_distinguishing_word_is_shared():
    """The fix shouldn't overcorrect — a real match on a short name (the
    distinguishing word "NYAGACHO" itself is shared, not just boilerplate)
    must still pass, verbose header and all."""
    detected = DetectedLocation(
        county="Nyamira", constituency="West Mugirango", ward="Bogichora",
        polling_station="NYAGACHO PRIMARY SCHOOL POLLING STATION 1 of 2",
    )
    mismatches = location_mismatches(detected, _station(station_name="Nyagacho Primary School"))
    assert mismatches == []
