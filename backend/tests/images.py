"""Synthetic test photos."""

from io import BytesIO

import numpy as np
from PIL import Image

EXIF_MAKE, EXIF_MODEL, EXIF_SERIAL = 0x010F, 0x0110, 0xA431


def road_photo(seed: int, size: tuple[int, int] = (640, 480), with_exif: bool = True) -> bytes:
    """A textured 'road' with a dark 'pothole'. Different seeds give different phashes."""
    rng = np.random.default_rng(seed)
    w, h = size
    coarse = rng.integers(60, 200, size=(12, 16, 3), dtype=np.uint8)
    img = Image.fromarray(coarse).resize((w, h), Image.BICUBIC)
    arr = np.asarray(img).astype(np.int16)
    arr += rng.integers(-20, 20, size=arr.shape, dtype=np.int16)
    cy, cx = h // 2 + int(rng.integers(-60, 60)), w // 2 + int(rng.integers(-80, 80))
    yy, xx = np.ogrid[:h, :w]
    arr[((yy - cy) / 60) ** 2 + ((xx - cx) / 90) ** 2 <= 1] = 25
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

    buf = BytesIO()
    if with_exif:
        exif = Image.Exif()
        exif[EXIF_MAKE] = "TestPhoneCo"
        exif[EXIF_MODEL] = "Model X"
        exif.get_ifd(0x8769)[EXIF_SERIAL] = "SERIAL-123456"
        img.save(buf, format="JPEG", quality=90, exif=exif)
    else:
        img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def blank_photo() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (640, 480), (128, 128, 128)).save(buf, format="JPEG")
    return buf.getvalue()
