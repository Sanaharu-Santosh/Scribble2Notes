"""Mode 1 — Lens: detect text in place and return it with its coordinates."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import image_upload
from app.schemas.lens import LensResult
from app.services.ocr.registry import get_ocr_engine

router = APIRouter(prefix="/lens", tags=["lens"])


@router.post("", response_model=LensResult)
async def recognize(image: bytes = Depends(image_upload)) -> LensResult:
    """Return every text region found in the image, in source-pixel coordinates.

    The image itself is not modified and not stored — the frontend keeps the
    original and draws a transparent, positioned text layer on top of it.
    """
    engine = get_ocr_engine()
    return await engine.recognize(image)
