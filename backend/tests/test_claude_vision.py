import base64
import io

import anthropic
import pytest
from PIL import Image

from app.services.claude_vision import ClaudeExtractionService, MAX_DIMENSION, _prepare_image
from app.utils.errors import ApiError


class _FakeAPIError(anthropic.APIError):
    """anthropic.APIError's real constructor wants a live httpx request —
    not worth constructing for a unit test that only cares that our code
    catches the base class and converts it to a clean ApiError."""

    def __init__(self, message):
        Exception.__init__(self, message)
        self.message = message


def test_prepare_image_downscales_beyond_max_dimension(tmp_path):
    path = tmp_path / "big.png"
    Image.new("RGB", (3000, 2200), (200, 200, 200)).save(path)

    b64, media_type = _prepare_image(str(path))

    assert media_type == "image/jpeg"
    decoded = Image.open(io.BytesIO(base64.b64decode(b64)))
    assert max(decoded.size) <= MAX_DIMENSION


def test_prepare_image_leaves_small_images_alone(tmp_path):
    path = tmp_path / "small.png"
    Image.new("RGB", (400, 300), (10, 20, 30)).save(path)

    b64, _ = _prepare_image(str(path))

    decoded = Image.open(io.BytesIO(base64.b64decode(b64)))
    assert decoded.size == (400, 300)


def test_prepare_image_flattens_transparency_onto_white_not_black(tmp_path):
    path = tmp_path / "transparent.png"
    Image.new("RGBA", (100, 100), (0, 0, 0, 0)).save(path)

    b64, _ = _prepare_image(str(path))

    decoded = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    assert decoded.getpixel((50, 50)) == (255, 255, 255)


def test_api_failure_surfaces_as_a_clean_error_not_a_500(tmp_path):
    path = tmp_path / "form.png"
    Image.new("RGB", (400, 300), (200, 200, 200)).save(path)

    service = ClaudeExtractionService.__new__(ClaudeExtractionService)

    class _FakeMessages:
        def create(self, **kwargs):
            raise _FakeAPIError("Your credit balance is too low to access the Anthropic API.")

    class _FakeClient:
        messages = _FakeMessages()

    service.client = _FakeClient()

    from app.models import ElectivePosition

    position = ElectivePosition(name="president", form_series="34", level="national")

    with pytest.raises(ApiError) as exc_info:
        service.extract(str(path), position, "34A")
    assert exc_info.value.status_code == 503
    assert "temporarily unavailable" in exc_info.value.message
