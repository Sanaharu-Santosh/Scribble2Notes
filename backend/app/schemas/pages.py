"""Saved pages, over the wire."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PageCreate(BaseModel):
    title: str = Field(default="Untitled page", max_length=200)
    page_width: int = Field(gt=0)
    page_height: int = Field(gt=0)
    scene: list[dict] = Field(default_factory=list)


class PageUpdate(BaseModel):
    """Both optional: a rename shouldn't have to resend the whole scene."""

    title: str | None = Field(default=None, max_length=200)
    scene: list[dict] | None = None


class PageSummary(BaseModel):
    """What the list view needs — deliberately without the scene, which is the
    large part and useless until a page is actually opened."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    page_width: int
    page_height: int
    has_scan: bool
    element_count: int
    created_at: datetime
    updated_at: datetime


class PageDetail(PageSummary):
    scene: list[dict]
