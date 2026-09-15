"""Inkwell API entry point."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import health, lens, scan
from app.config import get_settings
from app.services.images import UnreadableImageError
from app.services.layout.base import LayoutEngineError
from app.services.ocr.base import OcrEngineError

DESCRIPTION = """
Two modes, one shared engine seam.

* **Lens** (`POST /api/lens`) — detect text in place and return it with the
  coordinates needed to draw a selectable overlay on top of the original image.
* **Scan** (`POST /api/scan`) — decompose a page into typed blocks (paragraphs,
  tables, figures) that a canvas editor can turn into editable objects.

Which implementation serves each mode is set by `OCR_ENGINE` and `LAYOUT_ENGINE`.
Both default to `mock`, so the app runs end to end with no credentials.
""".strip()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=f"{settings.app_name} API",
        description=DESCRIPTION,
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(lens.router, prefix="/api")
    app.include_router(scan.router, prefix="/api")

    @app.exception_handler(UnreadableImageError)
    async def _unreadable_image(_: Request, exc: UnreadableImageError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})

    @app.exception_handler(OcrEngineError)
    @app.exception_handler(LayoutEngineError)
    async def _engine_unavailable(_: Request, exc: Exception) -> JSONResponse:
        # 503 rather than 500: the request was fine, the configured engine was not.
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": str(exc)}
        )

    return app


app = create_app()
