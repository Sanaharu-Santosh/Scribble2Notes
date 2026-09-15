"""Mode 2 — Scan & Edit: decompose a page into typed, placeable blocks."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import image_upload
from app.schemas.scan import DocumentStructure
from app.services.layout.registry import get_layout_engine

router = APIRouter(prefix="/scan", tags=["scan"])


@router.post("", response_model=DocumentStructure)
async def analyze(image: bytes = Depends(image_upload)) -> DocumentStructure:
    """Return the page's blocks in reading order, ready to place on the canvas."""
    engine = get_layout_engine()
    return await engine.analyze(image)
