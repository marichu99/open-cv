from PIL import Image

from app.services.image_quality import looks_blank


def test_blank_image_is_flagged(tmp_path):
    path = tmp_path / "blank.png"
    Image.new("L", (200, 200), 255).save(path)
    assert looks_blank(str(path)) is True


def test_image_with_real_variance_is_not_flagged(tmp_path):
    path = tmp_path / "form.png"
    img = Image.new("L", (200, 200), 255)
    # A few dark blocks stand in for printed text/table lines — enough
    # variance that this shouldn't read as a blank page.
    for x in range(0, 200, 20):
        for y in range(0, 200, 10):
            img.putpixel((x, y), 0)
    img.save(path)
    assert looks_blank(str(path)) is False


def test_undecodable_file_is_not_flagged_as_blank(tmp_path):
    path = tmp_path / "not-an-image.jpg"
    path.write_bytes(b"this is not real image data")
    assert looks_blank(str(path)) is False
