"""Shared request dependencies."""

from __future__ import annotations

from fastapi import File, HTTPException, UploadFile, status

from app.config import get_settings

ALLOWED_PREFIXES = ("image/",)


async def image_upload(file: UploadFile = File(..., description="Page photo or scan")) -> bytes:
    """Validate and read an uploaded image into memory.

    Size is checked after reading because ``UploadFile`` does not expose a
    trustworthy length up front. At the Phase 0 limit (10 MB) that is fine; if
    multi-page PDFs arrive in a later phase, switch to streaming to disk.
    """
    settings = get_settings()

    if not (file.content_type or "").startswith(ALLOWED_PREFIXES):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Expected an image upload, got {file.content_type or 'unknown'}",
        )

    payload = await file.read()
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty",
        )

    if len(payload) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image is larger than the {settings.max_upload_mb} MB limit",
        )

    return payload
