"""The opencv layout engine: structure from CV, text from the OCR seam."""

from __future__ import annotations

import asyncio
from pathlib import Path

import cv2
import pytest

from app.schemas.common import EngineInfo, Quad, TextRegion
from app.schemas.lens import LensResult
from app.schemas.scan import BlockType
from app.services.layout.detect import find_grids
from app.services.layout.opencv_engine import OpenCvLayoutEngine
from app.services.ocr.base import OcrEngine, OcrEngineError
from tests.conftest import use_settings

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
PAGE = FIXTURES / "structured_page.png"


@pytest.fixture(scope="module")
def page_bytes() -> bytes:
    if not PAGE.exists():
        pytest.skip("run: python fixtures/make_structured_page.py")
    return PAGE.read_bytes()


def analyze(image: bytes):
    return asyncio.run(OpenCvLayoutEngine().analyze(image))


class StubOcrEngine(OcrEngine):
    """Returns regions at coordinates we choose, so filing can be asserted."""

    name = "stub"
    is_mock = True

    def __init__(self, regions: list[TextRegion]) -> None:
        self._regions = regions

    async def recognize(self, image: bytes) -> LensResult:
        return LensResult(
            image_width=1240,
            image_height=1754,
            regions=self._regions,
            full_text="",
            engine=EngineInfo(name=self.name, duration_ms=0, is_mock=True),
        )


class BrokenOcrEngine(OcrEngine):
    name = "broken"

    async def recognize(self, image: bytes) -> LensResult:
        raise OcrEngineError("no credentials")


def _region(text: str, x: float, y: float, w: float = 60, h: float = 24) -> TextRegion:
    return TextRegion(
        id=f"stub-{text}", text=text, quad=Quad.from_bbox(x, y, w, h), confidence=0.9, level="line"
    )


# --------------------------------------------------------------------------
# Structure
# --------------------------------------------------------------------------


def test_the_page_decomposes_into_the_expected_kinds(page_bytes, monkeypatch):
    use_settings(monkeypatch, layout_fill_text="false")
    result = analyze(page_bytes)

    kinds = [block.type for block in result.blocks]
    assert BlockType.HEADING in kinds
    assert BlockType.TABLE in kinds
    assert kinds.count(BlockType.PARAGRAPH) >= 3
    assert result.page_width == 1240


def test_the_table_arrives_as_a_real_grid(page_bytes, monkeypatch):
    use_settings(monkeypatch, layout_fill_text="false")
    table = next(b for b in analyze(page_bytes).blocks if b.type == BlockType.TABLE)

    assert table.table is not None
    assert (table.table.rows, table.table.cols) == (4, 3)
    assert len(table.table.cells) == 12


def test_reading_order_is_a_clean_top_to_bottom_sequence(page_bytes, monkeypatch):
    use_settings(monkeypatch, layout_fill_text="false")
    blocks = analyze(page_bytes).blocks

    assert [b.reading_order for b in blocks] == list(range(len(blocks)))
    tops = [b.quad.bbox.y for b in blocks]
    assert tops == sorted(tops)


# --------------------------------------------------------------------------
# Annotations land on the right block
# --------------------------------------------------------------------------


def test_underline_and_highlight_attach_to_the_same_paragraph(page_bytes, monkeypatch):
    use_settings(monkeypatch, layout_fill_text="false")
    blocks = analyze(page_bytes).blocks

    carrying = [b for b in blocks if b.annotations]
    kinds = {a.kind for b in carrying for a in b.annotations}
    assert {"underline", "highlight"} <= kinds

    # Both sit on body text, so neither should have been filed on the heading.
    for block in carrying:
        if any(a.kind in {"underline", "highlight"} for a in block.annotations):
            assert block.type is not BlockType.HEADING


def test_a_box_annotates_the_text_it_surrounds(page_bytes, monkeypatch):
    """Regression: the proximity rule used for underlines never matches a box,
    because a box sits above its text rather than below it. That silently turned
    every boxed paragraph into an empty figure."""
    use_settings(monkeypatch, layout_fill_text="false")
    blocks = analyze(page_bytes).blocks

    boxed = [b for b in blocks if any(a.kind == "box" for a in b.annotations)]
    assert len(boxed) == 1
    assert boxed[0].type is BlockType.PARAGRAPH
    assert not [b for b in blocks if b.type is BlockType.FIGURE]


# --------------------------------------------------------------------------
# Composition with the OCR seam
# --------------------------------------------------------------------------


def test_recognized_text_is_filed_into_the_cell_it_sits_in(page_bytes, monkeypatch):
    image = cv2.imread(str(PAGE))
    table_grid = next(grid for grid in find_grids(image) if grid.is_table)

    regions = []
    for row in range(table_grid.rows):
        for column in range(table_grid.columns):
            x, y, w, h = table_grid.cell_rect(row, column)
            regions.append(_region(f"r{row}c{column}", x + w / 2 - 20, y + h / 2 - 10))

    monkeypatch.setattr(
        "app.services.ocr.registry.get_ocr_engine", lambda: StubOcrEngine(regions)
    )
    use_settings(monkeypatch, layout_fill_text="true")

    table = next(b for b in analyze(page_bytes).blocks if b.type == BlockType.TABLE)
    lookup = {(cell.row, cell.col): cell.text for cell in table.table.cells}

    assert lookup[(0, 0)] == "r0c0"
    assert lookup[(2, 1)] == "r2c1"
    assert lookup[(3, 2)] == "r3c2"


def test_structure_survives_when_the_ocr_engine_fails(page_bytes, monkeypatch):
    """Structure without text is still useful. Failing the whole scan because a
    key expired would not be."""
    monkeypatch.setattr("app.services.ocr.registry.get_ocr_engine", lambda: BrokenOcrEngine())
    use_settings(monkeypatch, layout_fill_text="true")

    result = analyze(page_bytes)

    assert len(result.blocks) > 3
    assert all(block.text is None for block in result.blocks)


def test_text_filling_can_be_turned_off(page_bytes, monkeypatch):
    calls: list[int] = []

    def _engine():
        calls.append(1)
        return StubOcrEngine([])

    monkeypatch.setattr("app.services.ocr.registry.get_ocr_engine", _engine)
    use_settings(monkeypatch, layout_fill_text="false")

    analyze(page_bytes)

    assert calls == []  # no OCR call made at all
