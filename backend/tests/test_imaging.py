from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from app.imaging.sanitize import InvalidImage, obscure, sanitize
from tests.images import road_photo


def test_input_really_has_exif():
    exif = Image.open(BytesIO(road_photo(1))).getexif()
    assert exif.get(0x010F) == "TestPhoneCo"


def test_sanitize_strips_all_metadata():
    out = sanitize(road_photo(1))
    img = Image.open(BytesIO(out.jpeg))
    assert dict(img.getexif()) == {}
    assert "exif" not in img.info and "icc_profile" not in img.info
    for needle in (b"TestPhoneCo", b"Model X", b"SERIAL-123456"):
        assert needle not in out.jpeg


def test_sanitize_downscales_large_images():
    out = sanitize(road_photo(2, size=(4000, 3000)))
    assert max(out.width, out.height) == 1600


def test_phash_is_stable_and_distinguishes_photos():
    assert sanitize(road_photo(3)).phash == sanitize(road_photo(3)).phash
    assert sanitize(road_photo(3)).phash != sanitize(road_photo(4)).phash
    assert len(sanitize(road_photo(3)).phash) == 16


def test_obscure_changes_only_the_box():
    rng = np.random.default_rng(0)
    img = rng.integers(0, 255, size=(200, 200, 3), dtype=np.uint8)
    out = obscure(img, [(50, 50, 40, 40)], pad=0)
    assert not np.array_equal(out[50:90, 50:90], img[50:90, 50:90])
    assert np.array_equal(out[:50], img[:50])
    assert np.array_equal(out[100:], img[100:])
    # Detail is destroyed: the blurred patch has far less variation than the original.
    assert out[50:90, 50:90].std() < img[50:90, 50:90].std() / 3


def test_invalid_image_rejected():
    with pytest.raises(InvalidImage):
        sanitize(b"not an image")
