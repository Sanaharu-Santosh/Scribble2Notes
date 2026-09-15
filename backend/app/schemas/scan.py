"""Mode 2 (Scan & Edit) response shape.

Mode 2 answers a harder question than "what does this say" — it answers "what
*kind* of thing is this", because each kind becomes a different editable object
on the canvas. A paragraph becomes a text box; a table becomes a real grid; an
underline becomes a vector stroke attached to a span of text.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import EngineInfo, Quad


class BlockType(StrEnum):
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    LIST_ITEM = "list_item"
    TABLE = "table"
    FIGURE = "figure"


class TableCell(BaseModel):
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    text: str
    quad: Quad


class Table(BaseModel):
    rows: int
    cols: int
    cells: list[TableCell]


class Annotation(BaseModel):
    """Output of the bespoke CV pass (see docs/architecture.md).

    No mainstream layout model ships an "is this underlined" or "is this
    highlighted" class, so these come from our own OpenCV pass layered on top of
    the layout engine's output: HSV thresholding for highlighter colour, and
    horizontal-line detection under a text baseline for underlines.
    """

    kind: Literal["underline", "highlight", "box"]
    quad: Quad
    color: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class Block(BaseModel):
    id: str
    type: BlockType
    quad: Quad
    reading_order: int
    text: str | None = None
    table: Table | None = None
    figure_ref: str | None = Field(
        default=None,
        description="Storage key for a cropped figure/sketch region, set in Phase 5.",
    )
    annotations: list[Annotation] = Field(default_factory=list)


class DocumentStructure(BaseModel):
    """A single scanned page, decomposed into placeable editable objects."""

    page_width: int
    page_height: int
    blocks: list[Block]
    engine: EngineInfo
