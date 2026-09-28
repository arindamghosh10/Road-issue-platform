"""Photo sanitization: make a citizen's photo safe to show to government and public.

What it does, in order:
1. Decode the upload and apply the EXIF orientation (so the picture is upright).
2. Rebuild the image from raw pixels only. Re-encoding pixels drops ALL metadata:
   EXIF (GPS, device make/model/serial, timestamps), XMP, maker notes.
3. Downscale to at most 1600 px on the long side (smaller files, less incidental detail).
4. Detect faces and number plates and pixelate + blur them.
5. Compute a perceptual hash ("phash") used to spot the same photo being re-submitted.

Why OpenCV Haar cascades for detection? They are free, ship inside the opencv package
(no model download), run on CPU in milliseconds and need no GPU. They miss some faces
at odd angles and some Indian plate styles; a stronger detector (e.g. YuNet for faces,
a YOLO plate model) can be dropped in behind `detect_sensitive_regions` later.
"""

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from io import BytesIO

import cv2
import imagehash
import numpy as np
from PIL import Image, ImageOps

MAX_SIDE_PX = 1600
MAX_INPUT_PIXELS = 50_000_000  # guards against "decompression bomb" images

Image.MAX_IMAGE_PIXELS = MAX_INPUT_PIXELS

EXIF_DATETIME_ORIGINAL = 0x9003
EXIF_IFD = 0x8769

Box = tuple[int, int, int, int]  # x, y, width, height


class InvalidImage(ValueError):
    pass


@dataclass
class SanitizedImage:
    jpeg: bytes  # metadata-free, blurred JPEG — safe for gov/public
    width: int
    height: int
    faces_blurred: int
    plates_blurred: int
    phash: str  # 16 hex chars = 64-bit perceptual hash of the un-blurred pixels
    exif_captured_at: datetime | None  # read from the ORIGINAL, for verification only


@lru_cache
def _cascade(name: str) -> cv2.CascadeClassifier:
    return cv2.CascadeClassifier(cv2.data.haarcascades + name)


def detect_sensitive_regions(bgr: np.ndarray) -> tuple[list[Box], list[Box]]:
    """Return (face boxes, number-plate boxes) in pixel coordinates."""
    gray = cv2.equalizeHist(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
    faces = _cascade("haarcascade_frontalface_default.xml").detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24)
    )
    profiles = _cascade("haarcascade_profileface.xml").detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24)
    )
    plates = _cascade("haarcascade_russian_plate_number.xml").detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 12)
    )
    face_boxes = [tuple(map(int, b)) for b in (*faces, *profiles)]
    return face_boxes, [tuple(map(int, b)) for b in plates]


def obscure(bgr: np.ndarray, boxes: list[Box], pad: float = 0.15) -> np.ndarray:
    """Pixelate then blur each box (plus padding). Pixelating first destroys detail that a
    plain blur can sometimes leave recoverable."""
    out = bgr.copy()
    h, w = out.shape[:2]
    for x, y, bw, bh in boxes:
        px, py = int(bw * pad), int(bh * pad)
        x0, y0 = max(0, x - px), max(0, y - py)
        x1, y1 = min(w, x + bw + px), min(h, y + bh + py)
        region = out[y0:y1, x0:x1]
        if region.size == 0:
            continue
        # INTER_AREA averages every pixel in each block (INTER_LINEAR would only sample a
        # few, leaving recognisable detail behind).
        small = cv2.resize(region, (8, 8), interpolation=cv2.INTER_AREA)
        region = cv2.resize(small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)
        k = max(3, (min(x1 - x0, y1 - y0) // 4) | 1)  # odd kernel size
        out[y0:y1, x0:x1] = cv2.GaussianBlur(region, (k, k), 0)
    return out


def _exif_datetime(img: Image.Image) -> datetime | None:
    try:
        raw = img.getexif().get_ifd(EXIF_IFD).get(EXIF_DATETIME_ORIGINAL)
        # EXIF stores local time with no timezone; the capture check allows for that.
        return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S") if raw else None  # noqa: DTZ007
    except (ValueError, TypeError, AttributeError):
        return None


def sanitize(raw: bytes) -> SanitizedImage:
    try:
        img = Image.open(BytesIO(raw))
        img.load()
    except (Image.DecompressionBombError, OSError, SyntaxError) as exc:
        raise InvalidImage(f"could not read image: {exc}") from exc

    exif_dt = _exif_datetime(img)
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX))
    phash = str(imagehash.phash(img))

    bgr = np.array(img)[:, :, ::-1].copy()
    faces, plates = detect_sensitive_regions(bgr)
    bgr = obscure(bgr, faces + plates)

    # Build a brand-new image from pixels only: nothing from the original file survives.
    clean = Image.fromarray(np.ascontiguousarray(bgr[:, :, ::-1]), mode="RGB")
    buf = BytesIO()
    clean.save(buf, format="JPEG", quality=85, optimize=True)
    return SanitizedImage(
        jpeg=buf.getvalue(),
        width=clean.width,
        height=clean.height,
        faces_blurred=len(faces),
        plates_blurred=len(plates),
        phash=phash,
        exif_captured_at=exif_dt,
    )
