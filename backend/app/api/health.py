"""Liveness and configuration introspection."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    environment: str
    ocr_engine: str
    layout_engine: str
    using_mocks: bool


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report which engines this process is configured to use.

    The frontend calls this on load so the UI can say plainly when it is showing
    mock output — the single most confusing thing to forget during development.
    """
    settings = get_settings()
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        ocr_engine=settings.ocr_engine,
        layout_engine=settings.layout_engine,
        using_mocks=settings.ocr_engine == "mock" or settings.layout_engine == "mock",
    )
