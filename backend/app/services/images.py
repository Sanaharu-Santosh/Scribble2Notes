"""Small image helpers shared by every engine."""

from __future__ import annotations

import io
import math

from PIL import Image, UnidentifiedImageError

from app.schemas.common import Point, Quad


def _lerp(start: Point, end: Point, t: float) -> Point:
    return Point(x=start.x + (end.x - start.x) * t, y=start.y + (end.y - start.y) * t)


def sub_quad(quad: Quad, start: float, end: float) -> Quad:
    """Slice a quad along its length, as fractions from 0 to 1.

    Used to address part of a line — a single word inside it, or the span an
    underline sits beneath — while keeping the line's slant.
    """
    top_left, top_right, bottom_right, bottom_left = quad.points
    return Quad(
        points=[
            _lerp(top_left, top_right, start),
            _lerp(top_left, top_right, end),
            _lerp(bottom_left, bottom_right, end),
            _lerp(bottom_left, bottom_right, start),
        ]
    )


class UnreadableImageError(ValueError):
    """The uploaded bytes are not an image we can decode."""


def read_image_size(image: bytes) -> tuple[int, int]:
    """Return ``(width, height)`` in pixels, without decoding the full raster."""
    try:
        with Image.open(io.BytesIO(image)) as img:
            return img.width, img.height
    except (UnidentifiedImageError, OSError) as exc:  # pragma: no cover - passthrough
        raise UnreadableImageError("Could not decode the uploaded image") from exc


def scale_quad(quad: Quad, scale_x: float, scale_y: float) -> Quad:
    """Scale every corner — for mapping coordinates between image sizes."""
    return Quad(points=[Point(x=p.x * scale_x, y=p.y * scale_y) for p in quad.points])


def slanted_quad(x: float, y: float, width: float, height: float, angle_deg: float) -> Quad:
    """Build a quad rotated by ``angle_deg`` about its top-left corner."""
    rad = math.radians(angle_deg)
    cos, sin = math.cos(rad), math.sin(rad)

    def corner(dx: float, dy: float) -> Point:
        return Point(x=x + dx * cos - dy * sin, y=y + dx * sin + dy * cos)

    return Quad(points=[corner(0, 0), corner(width, 0), corner(width, height), corner(0, height)])
