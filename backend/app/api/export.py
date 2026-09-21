"""Phase 4 — turn the edited canvas into a file."""

from __future__ import annotations

import re

from fastapi import APIRouter
from fastapi.responses import Response

from app.schemas.export import ExportDocument
from app.services.export.docx_builder import build_docx
from app.services.export.pdf_builder import build_pdf

router = APIRouter(prefix="/export", tags=["export"])

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _filename(title: str | None, extension: str) -> str:
    """A safe download name. Titles come from the page, so from the user."""
    stem = re.sub(r"[^A-Za-z0-9 _-]+", "", (title or "").strip())[:60].strip()
    return f"{(stem or 'notes').replace(' ', '-')}.{extension}"


def _attachment(payload: bytes, media_type: str, filename: str) -> Response:
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/docx")
async def export_docx(document: ExportDocument) -> Response:
    """Flowed and editable: real headings, paragraphs and Word tables.

    Positions are dropped in favour of reading order — the point is a document
    you can keep working on in Word, not a picture of the page.
    """
    return _attachment(build_docx(document), DOCX_MEDIA_TYPE, _filename(document.title, "docx"))


@router.post("/pdf")
async def export_pdf(document: ExportDocument) -> Response:
    """Positioned and searchable: the page as arranged, with text still text."""
    return _attachment(build_pdf(document), "application/pdf", _filename(document.title, "pdf"))
