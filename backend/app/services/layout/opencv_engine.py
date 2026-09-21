"""Mode 2 structure from classical CV, text from the OCR seam.

This engine answers "what kind of thing is this and where" with morphology
(:mod:`app.services.layout.detect`), then — if an OCR engine is configured —
asks it what the page says and files each recognized region into the block or
table cell it falls inside.

That split is the point. Structure and recognition are genuinely different
problems: ruled tables and highlighter marks are geometry and colour, best found
with lines and thresholds; reading handwriting is a model's job. Composing them
means Mode 2 improves automatically every time Mode 1's engine gets better, and
that neither half has to be rewritten when the other changes.

No model weights, no downloads, no GPU — which also makes it the sane default
for a notes app, where the tables are ruled with a pen rather than typeset.
"""

from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image

from app.config import get_settings
from app.schemas.common import Quad, TextRegion
from app.schemas.scan import Annotation, Block, BlockType, DocumentStructure, Table, TableCell
from app.services.layout.base import LayoutEngine, LayoutEngineError
from app.services.layout.detect import (
    Grid,
    Rect,
    TextBlock,
    find_grids,
    find_highlights,
    find_text_blocks,
    find_underlines,
)

# A block whose lines are this much taller than the page's median line is a
# heading. Compared per line, never per block — see TextBlock.line_height.
HEADING_LINE_RATIO = 1.15


def _quad(rect: Rect) -> Quad:
    x, y, w, h = rect
    return Quad.from_bbox(float(x), float(y), float(w), float(h))


def _center(region: TextRegion) -> tuple[float, float]:
    box = region.quad.bbox
    return box.x + box.width / 2, box.y + box.height / 2


def _contains(rect: Rect, point: tuple[float, float]) -> bool:
    x, y, w, h = rect
    return x <= point[0] <= x + w and y <= point[1] <= y + h


def _text_for(rect: Rect, regions: list[TextRegion]) -> str | None:
    """Join the recognized regions whose centre falls inside ``rect``.

    Centre-point containment rather than overlap: a line of text that pokes a
    few pixels past a cell border still belongs to that cell, and overlap tests
    would hand it to both neighbours.
    """
    inside = [region for region in regions if _contains(rect, _center(region))]
    if not inside:
        return None
    inside.sort(key=lambda region: (region.quad.bbox.y, region.quad.bbox.x))
    return " ".join(region.text for region in inside).strip() or None


def _attach(annotation_rect: Rect, blocks: list[Block], margin: int) -> Block | None:
    """Find the block an underline or highlight belongs to.

    Horizontal overlap plus vertical proximity: an underline sits just *below*
    its words, so a containment test would never match it.
    """
    ax, ay, aw, _ = annotation_rect
    best: tuple[float, Block] | None = None

    for block in blocks:
        box = block.quad.bbox
        overlap = min(ax + aw, box.x + box.width) - max(ax, box.x)
        if overlap <= 0:
            continue
        if not (box.y - margin <= ay <= box.y + box.height + margin):
            continue
        distance = abs(ay - (box.y + box.height))
        if best is None or distance < best[0]:
            best = (distance, block)

    return best[1] if best else None


def _containing_block(rect: Rect, blocks: list[Block]) -> Block | None:
    """The block sitting inside ``rect`` — for boxes drawn around text."""
    x, y, w, h = rect
    for block in blocks:
        box = block.quad.bbox
        center = (box.x + box.width / 2, box.y + box.height / 2)
        if x <= center[0] <= x + w and y <= center[1] <= y + h:
            return block
    return None


class OpenCvLayoutEngine(LayoutEngine):
    name = "opencv"

    async def analyze(self, image: bytes) -> DocumentStructure:
        started = self._now()
        settings = get_settings()

        try:
            with Image.open(io.BytesIO(image)) as opened:
                rgb = opened.convert("RGB")
                width, height = rgb.width, rgb.height
                array = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)
        except OSError as exc:
            raise LayoutEngineError(f"Could not decode the image: {exc}") from exc

        grids = find_grids(array)
        tables = [grid for grid in grids if grid.is_table]
        boxes = [grid for grid in grids if not grid.is_table]
        text_blocks = find_text_blocks(array, exclude=tables)

        regions = await self._recognize(image) if settings.layout_fill_text else []

        blocks = self._build_blocks(text_blocks, tables, regions)
        self._attach_annotations(array, blocks, boxes, grids, height)

        for order, block in enumerate(sorted(blocks, key=lambda b: (b.quad.bbox.y, b.quad.bbox.x))):
            block.reading_order = order

        return DocumentStructure(
            page_width=width,
            page_height=height,
            blocks=sorted(blocks, key=lambda block: block.reading_order),
            engine=self._engine_info(started),
        )

    async def _recognize(self, image: bytes) -> list[TextRegion]:
        """Ask the configured Mode 1 engine what the page says.

        A failure here is not fatal: structure without text is still useful, and
        far better than failing the whole scan because an API key expired.
        """
        from app.services.ocr.base import OcrEngineError  # noqa: PLC0415
        from app.services.ocr.registry import get_ocr_engine  # noqa: PLC0415

        try:
            return (await get_ocr_engine().recognize(image)).regions
        except (OcrEngineError, ValueError):
            return []

    def _build_blocks(
        self, text_blocks: list[TextBlock], tables: list[Grid], regions: list[TextRegion]
    ) -> list[Block]:
        blocks: list[Block] = []

        line_heights = sorted(block.line_height for block in text_blocks)
        median = line_heights[len(line_heights) // 2] if line_heights else 0.0

        for index, text_block in enumerate(text_blocks):
            is_heading = median > 0 and text_block.line_height >= median * HEADING_LINE_RATIO
            blocks.append(
                Block(
                    id=f"cv-block-{index}",
                    type=BlockType.HEADING if is_heading else BlockType.PARAGRAPH,
                    quad=_quad(text_block.rect),
                    reading_order=index,
                    text=_text_for(text_block.rect, regions),
                    line_count=text_block.line_count,
                )
            )

        for index, grid in enumerate(tables):
            cells = [
                TableCell(
                    row=row,
                    col=column,
                    text=_text_for(grid.cell_rect(row, column), regions) or "",
                    quad=_quad(grid.cell_rect(row, column)),
                )
                for row in range(grid.rows)
                for column in range(grid.columns)
            ]
            blocks.append(
                Block(
                    id=f"cv-table-{index}",
                    type=BlockType.TABLE,
                    quad=_quad(grid.rect),
                    reading_order=len(blocks),
                    table=Table(rows=grid.rows, cols=grid.columns, cells=cells),
                )
            )

        return blocks

    def _attach_annotations(
        self,
        array: np.ndarray,
        blocks: list[Block],
        boxes: list[Grid],
        grids: list[Grid],
        height: int,
    ) -> None:
        margin = max(int(height * 0.02), 12)

        for rect in find_underlines(array, grids):
            target = _attach(rect, blocks, margin)
            if target:
                target.annotations.append(
                    Annotation(kind="underline", quad=_quad(rect), color="#1a1a1a")
                )

        for rect, color in find_highlights(array):
            target = _attach(rect, blocks, margin)
            if target:
                target.annotations.append(
                    Annotation(kind="highlight", quad=_quad(rect), color=color)
                )

        for index, grid in enumerate(boxes):
            # A box surrounds its text rather than sitting under it, so the
            # proximity rule used for underlines never matches — ask which
            # block the box contains instead.
            target = _containing_block(grid.rect, blocks)
            if target:
                target.annotations.append(Annotation(kind="box", quad=_quad(grid.rect)))
            else:
                # An empty drawn box is a diagram someone will fill in, not text.
                blocks.append(
                    Block(
                        id=f"cv-figure-{index}",
                        type=BlockType.FIGURE,
                        quad=_quad(grid.rect),
                        reading_order=len(blocks),
                    )
                )
