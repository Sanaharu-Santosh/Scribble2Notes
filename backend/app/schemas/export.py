"""What the canvas sends back when you ask for a file.

Deliberately *not* :class:`~app.schemas.scan.DocumentStructure`. That describes
what the engine detected; by export time the user has retyped paragraphs, moved
cells and drawn arrows, and exporting the detection would hand them back a file
that ignores every edit they made. So the canvas is read back into this schema
instead, and the exporters only ever see what is actually on screen.

Two exporters consume it, and they want different things from the same document:

* **DOCX** wants *flow* — headings, paragraphs and real Word tables in reading
  order, so the result is editable in Word like any other document. Exact
  positions are discarded.
* **PDF** wants *place* — every item where the user put it, so the page looks
  like what they were editing, with the text still selectable.

Each item therefore carries both its geometry and its role.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class ItemKind(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    FIGURE = "figure"
    LINE = "line"
    ARROW = "arrow"


class ExportMark(BaseModel):
    """An underline, highlight or box, with the geometry PDF needs to draw it."""

    kind: Literal["underline", "highlight", "box"]
    color: str | None = None
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0


class ExportCell(BaseModel):
    row: int
    col: int
    text: str = ""


class ExportTable(BaseModel):
    rows: int = Field(ge=1)
    cols: int = Field(ge=1)
    cells: list[ExportCell] = Field(default_factory=list)


class ExportItem(BaseModel):
    id: str
    kind: ItemKind
    x: float
    y: float
    width: float
    height: float
    reading_order: int = 0

    text: str | None = None
    font_size: float | None = None
    color: str | None = None
    background: str | None = None

    marks: list[ExportMark] = Field(default_factory=list)
    table: ExportTable | None = None
    points: list[tuple[float, float]] | None = Field(
        default=None, description="Relative to (x, y), for lines and arrows."
    )


class ExportDocument(BaseModel):
    page_width: float = Field(gt=0)
    page_height: float = Field(gt=0)
    title: str | None = None
    items: list[ExportItem] = Field(default_factory=list)

    def in_reading_order(self) -> list[ExportItem]:
        return sorted(self.items, key=lambda item: (item.reading_order, item.y, item.x))
