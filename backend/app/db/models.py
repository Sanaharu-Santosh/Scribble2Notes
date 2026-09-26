"""Database tables.

Two of them, and the shape of the second is the interesting decision.

A saved page keeps the *canvas scene*, not the detected structure. Detection is
a one-time derivation — re-running it on the original scan would throw away
every edit made since. The scene is the document; the scan is provenance.

The scan itself is not stored here. Base64 image data in a JSONB column would
make every row megabytes and every list query slow, so the bytes go through the
storage seam and the row keeps a key.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# Timezone-aware on purpose. A naive timestamp means "whatever zone the server
# happened to be in", which is fine until the app is deployed on a UTC host and
# read by someone who is not, and every "saved 3 hours ago" is wrong.
Timestamp = DateTime(timezone=True)


class User(Base):
    __tablename__ = "users"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120), default=None)
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())

    pages: Mapped[list[Page]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Page(Base):
    __tablename__ = "pages"

    # Fetch server-generated values (created_at, and updated_at after an UPDATE)
    # with RETURNING in the same statement. Without it SQLAlchemy marks those
    # attributes expired and refreshes them on next access — which, under async,
    # means IO from a synchronous property read and a MissingGreenlet error the
    # moment anything reads `updated_at` after a save.
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="Untitled page")

    page_width: Mapped[int]
    page_height: Mapped[int]

    # The Excalidraw elements, exactly as the canvas holds them. JSONB rather
    # than a normalised element table on purpose: nothing queries *into* a
    # scene, it is loaded and saved whole, and normalising it would mean
    # chasing Excalidraw's element schema forever.
    scene: Mapped[list[dict]] = mapped_column(JSONB, default=list)

    # Storage key for the original scan, not the bytes. Null once the user
    # deletes the scan but keeps the page.
    scan_key: Mapped[str | None] = mapped_column(String(300), default=None)

    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        Timestamp, server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped[User] = relationship(back_populates="pages")

    __table_args__ = (
        # The list view is always "my pages, newest first".
        Index("ix_pages_owner_updated", "owner_id", updated_at.desc()),
    )
