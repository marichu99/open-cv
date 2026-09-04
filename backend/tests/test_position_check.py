from app.services.position_check import position_mismatch


class _Position:
    def __init__(self, name):
        self.name = name


def test_no_mismatch_when_backend_does_not_detect_position():
    assert position_mismatch(None, _Position("president")) is None


def test_no_mismatch_when_detected_matches_declared():
    assert position_mismatch("president", _Position("president")) is None


def test_flags_a_genuinely_different_race():
    message = position_mismatch("woman_representative", _Position("president"))
    assert message is not None
    assert "Woman Representative" in message
    assert "President" in message


def test_message_names_both_the_detected_and_declared_race():
    message = position_mismatch("mca", _Position("senator"))
    assert "Member of County Assembly (MCA)" in message
    assert "Senator" in message
