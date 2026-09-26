"""Phase 5 — save a page and come back to it."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import image_upload
from app.db.models import Page
from app.db.session import get_session
from app.schemas.pages import PageCreate, PageDetail, PageSummary, PageUpdate
from app.services.auth import current_user
from app.services.storage.base import ObjectNotFound
from app.services.storage.registry import get_storage

router = APIRouter(prefix="/pages", tags=["pages"])


def _summary_fields(page: Page) -> dict:
    return {
        "id": page.id,
        "title": page.title,
        "page_width": page.page_width,
        "page_height": page.page_height,
        "has_scan": page.scan_key is not None,
        "element_count": len(page.scene or []),
        "created_at": page.created_at,
        "updated_at": page.updated_at,
    }


def _detail(page: Page) -> PageDetail:
    return PageDetail(**_summary_fields(page), scene=page.scene or [])


async def _owned_page(page_id: uuid.UUID, session: AsyncSession) -> Page:
    """Fetch a page belonging to the requesting user.

    Someone else's page is a 404, not a 403: a 403 would confirm the id exists,
    which is more than a stranger should learn.
    """
    user = await current_user(session)
    page = await session.scalar(
        select(Page).where(Page.id == page_id, Page.owner_id == user.id)
    )
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such page")
    return page


@router.post("", response_model=PageDetail, status_code=status.HTTP_201_CREATED)
async def create_page(body: PageCreate, session: AsyncSession = Depends(get_session)) -> PageDetail:
    user = await current_user(session)
    page = Page(
        owner_id=user.id,
        title=body.title,
        page_width=body.page_width,
        page_height=body.page_height,
        scene=body.scene,
    )
    session.add(page)
    await session.flush()
    return _detail(page)


@router.get("", response_model=list[PageSummary])
async def list_pages(session: AsyncSession = Depends(get_session)) -> list[PageSummary]:
    user = await current_user(session)
    pages = await session.scalars(
        select(Page).where(Page.owner_id == user.id).order_by(Page.updated_at.desc())
    )
    return [PageSummary(**_summary_fields(page)) for page in pages]


@router.get("/{page_id}", response_model=PageDetail)
async def read_page(
    page_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> PageDetail:
    return _detail(await _owned_page(page_id, session))


@router.put("/{page_id}", response_model=PageDetail)
async def update_page(
    page_id: uuid.UUID, body: PageUpdate, session: AsyncSession = Depends(get_session)
) -> PageDetail:
    page = await _owned_page(page_id, session)
    if body.title is not None:
        page.title = body.title
    if body.scene is not None:
        page.scene = body.scene
    await session.flush()
    return _detail(page)


@router.delete("/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_page(page_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> Response:
    page = await _owned_page(page_id, session)

    # Drop the scan first: a row without its blob is a broken page, a blob
    # without its row is only wasted bytes.
    if page.scan_key:
        await get_storage().delete(page.scan_key)

    await session.delete(page)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{page_id}/scan", response_model=PageSummary)
async def upload_scan(
    page_id: uuid.UUID,
    image: bytes = Depends(image_upload),
    session: AsyncSession = Depends(get_session),
) -> PageSummary:
    """Store the original image for a page.

    Separate from creating the page so that saving an edit doesn't re-upload the
    scan every time — it never changes after the first save.
    """
    page = await _owned_page(page_id, session)
    key = f"scans/{page.owner_id}/{page.id}.png"

    await get_storage().put(key, image, "image/png")
    page.scan_key = key
    await session.flush()
    return PageSummary(**_summary_fields(page))


@router.get("/{page_id}/scan")
async def read_scan(page_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> Response:
    page = await _owned_page(page_id, session)
    if not page.scan_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This page has no scan")

    try:
        data = await get_storage().get(page.scan_key)
    except ObjectNotFound as exc:
        # The row says there is a scan and storage disagrees. Worth a distinct
        # message: it means the two got out of sync, not that nothing was saved.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The scan for this page is missing from storage",
        ) from exc

    return Response(content=data, media_type="image/png")
