"""Small image helpers shared by every engine."""

from __future__ import annotations

import io
import math

from PIL import Image, UnidentifiedImageError

from app.schemas.common import Point, Quad


class UnreadableImageError(ValueError):
    """The uploaded bytes are not an image we can decode."""


def read_image_size(image: bytes) -> tuple[int, int]:
    """Return ``(width, height)`` in pixels, without decoding the full raster."""
    try:
        with Image.open(io.BytesIO(image)) as img:
            return img.width, img.height
    except (UnidentifiedImageError, OSError) as exc:  # pragma: no cover - passthrough
        raise UnreadableImageError("Could not decode the uploaded image") from exc


def slanted_quad(x: float, y: float, width: float, height: float, angle_deg: float) -> Quad:
    """Build a quad rotated by ``angle_deg`` about its top-left corner."""
    rad = math.radians(angle_deg)
    cos, sin = math.cos(rad), math.sin(rad)

    def corner(dx: float, dy: float) -> Point:
        return Point(x=x + dx * cos - dy * sin, y=y + dx * sin + dy * cos)

    return Quad(points=[corner(0, 0), corner(width, 0), corner(width, height), corner(0, height)])
