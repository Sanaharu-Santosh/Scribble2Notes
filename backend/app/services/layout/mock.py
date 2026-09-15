"""A deterministic stand-in for a real layout/structure engine.

Returns a plausible page — heading, paragraphs, a real table grid, a figure
region, plus one underline and one highlight annotation — scaled to whatever
image you upload. Phase 2 can build and verify the canvas reconstruction against
this before PP-StructureV3 is wired up, which keeps the two problems separate:
"does my canvas place blocks correctly" and "does my engine find them".
"""

from __future__ import annotations

from app.schemas.scan import Annotation, Block, BlockType, DocumentStructure, Table, TableCell
from app.services.images import read_image_size, slanted_quad
from app.services.layout.base import LayoutEngine

TABLE_ROWS = [
    ["Method", "CER", "Notes"],
    ["Greedy decode", "27%", "baseline"],
    ["Beam k=5", "19%", "+ dictionary"],
    ["Pretrained", "8%", "needs GPU"],
]


def _rect(x: float, y: float, w: float, h: float):
    return slanted_quad(x, y, w, h, 0.0)


class MockLayoutEngine(LayoutEngine):
    name = "mock"
    is_mock = True

    async def analyze(self, image: bytes) -> DocumentStructure:
        started = self._now()
        width, height = read_image_size(image)

        left = width * 0.08
        content_width = width * 0.84
        blocks: list[Block] = []

        blocks.append(
            Block(
                id="block-heading",
                type=BlockType.HEADING,
                quad=_rect(left, height * 0.06, content_width * 0.6, height * 0.05),
                reading_order=0,
                text="Unit 3 - Reading a page, not a word",
            )
        )

        blocks.append(
            Block(
                id="block-para-1",
                type=BlockType.PARAGRAPH,
                quad=_rect(left, height * 0.14, content_width, height * 0.10),
                reading_order=1,
                text=(
                    "Detection finds where the words are. Recognition reads them. "
                    "Layout analysis is the third thing: it decides what kind of "
                    "object each region is, which is what makes the page editable."
                ),
            )
        )

        # --- table -------------------------------------------------------
        table_top = height * 0.28
        table_height = height * 0.22
        row_height = table_height / len(TABLE_ROWS)
        col_width = content_width / len(TABLE_ROWS[0])
        cells = [
            TableCell(
                row=r,
                col=c,
                text=value,
                quad=_rect(left + c * col_width, table_top + r * row_height, col_width, row_height),
            )
            for r, row in enumerate(TABLE_ROWS)
            for c, value in enumerate(row)
        ]
        blocks.append(
            Block(
                id="block-table-1",
                type=BlockType.TABLE,
                quad=_rect(left, table_top, content_width, table_height),
                reading_order=2,
                table=Table(rows=len(TABLE_ROWS), cols=len(TABLE_ROWS[0]), cells=cells),
            )
        )

        # --- paragraph carrying annotations -------------------------------
        para_2_top = height * 0.54
        para_2_height = height * 0.10
        blocks.append(
            Block(
                id="block-para-2",
                type=BlockType.PARAGRAPH,
                quad=_rect(left, para_2_top, content_width, para_2_height),
                reading_order=3,
                text=(
                    "Underlines and highlights come from our own OpenCV pass - no "
                    "mainstream model reports them as classes, so we detect them "
                    "separately and attach them to the block they sit on."
                ),
                annotations=[
                    Annotation(
                        kind="underline",
                        quad=_rect(
                            left,
                            para_2_top + para_2_height * 0.36,
                            content_width * 0.28,
                            height * 0.004,
                        ),
                        color="#1a1a1a",
                        confidence=0.88,
                    ),
                    Annotation(
                        kind="highlight",
                        quad=_rect(
                            left + content_width * 0.30,
                            para_2_top + para_2_height * 0.62,
                            content_width * 0.34,
                            height * 0.030,
                        ),
                        color="#ffe14d",
                        confidence=0.76,
                    ),
                ],
            )
        )

        blocks.append(
            Block(
                id="block-figure-1",
                type=BlockType.FIGURE,
                quad=_rect(left, height * 0.68, content_width * 0.42, height * 0.20),
                reading_order=4,
                figure_ref=None,
            )
        )

        return DocumentStructure(
            page_width=width,
            page_height=height,
            blocks=blocks,
            engine=self._engine_info(started),
        )
