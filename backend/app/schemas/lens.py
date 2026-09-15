"""Mode 1 (Lens) response shape."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.common import EngineInfo, TextRegion


class LensResult(BaseModel):
    """Everything the frontend needs to draw a selectable text layer.

    ``image_width`` / ``image_height`` are the dimensions the region coordinates
    were computed against. The frontend divides its rendered size by these to get
    the scale factor for the overlay, so the two never drift apart.
    """

    image_width: int
    image_height: int
    regions: list[TextRegion]
    full_text: str
    engine: EngineInfo
