"""Cheap, local pre-filter for obviously unusable photos — a solid-color or
near-blank image can't contain a legible form no matter what, so there's no
reason to spend a Claude Vision call finding that out (we've paid for that
exact lesson before). Deliberately conservative: only catches near-uniform
images, never a real low-contrast/faded scan, which still has genuine
variance from printed text, lines, and the form's own bordered layout.
"""

from PIL import Image, ImageStat

BLANK_STDDEV_THRESHOLD = 6.0


def looks_blank(image_path: str) -> bool:
    # An undecodable file isn't this check's problem to solve — surface
    # whatever downstream (extraction, PDF conversion) already does with it
    # rather than crashing the upload on a corrupt-but-not-blank file.
    try:
        with Image.open(image_path) as img:
            stat = ImageStat.Stat(img.convert("L"))
            return stat.stddev[0] < BLANK_STDDEV_THRESHOLD
    except Exception:
        return False
