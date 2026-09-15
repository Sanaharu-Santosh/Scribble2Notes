"""The overlay is only as good as this maths, so it gets its own tests."""

from __future__ import annotations

import math

import pytest

from app.schemas.common import Quad
from app.services.images import slanted_quad


def test_axis_aligned_quad_round_trips():
    quad = Quad.from_bbox(10, 20, 100, 50)

    assert quad.bbox.x == 10
    assert quad.bbox.y == 20
    assert quad.bbox.width == 100
    assert quad.bbox.height == 50
    assert quad.angle_deg == pytest.approx(0.0)
    assert quad.height == pytest.approx(50.0)


def test_slanted_quad_reports_its_angle():
    width, height, angle = 100.0, 20.0, 30.0
    quad = slanted_quad(0, 0, width, height, angle)

    assert quad.angle_deg == pytest.approx(angle, abs=1e-6)
    # Rotation preserves the text height; only the bounding box changes shape.
    assert quad.height == pytest.approx(height, abs=1e-6)

    radians = math.radians(angle)
    expected_width = width * math.cos(radians) + height * math.sin(radians)
    expected_height = width * math.sin(radians) + height * math.cos(radians)
    assert quad.bbox.width == pytest.approx(expected_width, abs=1e-6)
    assert quad.bbox.height == pytest.approx(expected_height, abs=1e-6)


def test_quad_requires_exactly_four_points():
    with pytest.raises(ValueError):
        Quad(points=[{"x": 0, "y": 0}, {"x": 1, "y": 0}])
