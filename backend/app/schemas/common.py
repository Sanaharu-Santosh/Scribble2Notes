"""Geometry and shared types used by both modes.

Everything the OCR and layout engines return is expressed in **pixel coordinates
of the source image**, origin at top-left. The frontend scales these to whatever
size it happens to render the image at. Keeping the backend resolution-independent
is what lets the Lens overlay stay aligned at any zoom level or screen size.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field, computed_field

RegionLevel = Literal["word", "line", "paragraph"]


class Point(BaseModel):
    x: float
    y: float


class BBox(BaseModel):
    """Axis-aligned bounding box, in source-image pixels."""

    x: float
    y: float
    width: float
    height: float


class Quad(BaseModel):
    """Four corners of a region, clockwise from the top-left corner.

    A quad rather than a plain rectangle because handwriting is rarely
    axis-aligned: a line written on a slant needs its own rotation for the
    overlay text to sit *on* the ink rather than beside it. Engines that only
    return rectangles can use :meth:`from_bbox`.
    """

    points: list[Point] = Field(..., min_length=4, max_length=4)

    @classmethod
    def from_bbox(cls, x: float, y: float, width: float, height: float) -> Quad:
        return cls(
            points=[
                Point(x=x, y=y),
                Point(x=x + width, y=y),
                Point(x=x + width, y=y + height),
                Point(x=x, y=y + height),
            ]
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def bbox(self) -> BBox:
        """Tightest axis-aligned box containing the quad."""
        xs = [p.x for p in self.points]
        ys = [p.y for p in self.points]
        return BBox(x=min(xs), y=min(ys), width=max(xs) - min(xs), height=max(ys) - min(ys))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def angle_deg(self) -> float:
        """Rotation of the top edge, in degrees clockwise from horizontal."""
        tl, tr = self.points[0], self.points[1]
        return math.degrees(math.atan2(tr.y - tl.y, tr.x - tl.x))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def height(self) -> float:
        """Distance from the top edge to the bottom edge.

        Used by the frontend to size overlay text so a selection highlight
        matches the ink underneath it rather than the whole line box.
        """
        tl, bl = self.points[0], self.points[3]
        return math.hypot(bl.x - tl.x, bl.y - tl.y)


class TextRegion(BaseModel):
    """One recognized piece of text and where it sits on the page."""

    id: str
    text: str
    quad: Quad
    confidence: float = Field(ge=0.0, le=1.0)
    level: RegionLevel = "line"


class EngineInfo(BaseModel):
    """Which engine produced a result, and how long it took.

    Surfaced in every response so you can tell mock output from real output at a
    glance, and so swapping engines is visible in the UI during development.
    """

    name: str
    duration_ms: int
    is_mock: bool = False
