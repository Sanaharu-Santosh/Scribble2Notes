"""CV detection, checked against a page whose answers we wrote down.

``fixtures/make_structured_page.py`` draws the page and records exactly where it
put the table, the box, the underline and the highlight. That makes these real
assertions rather than "it found four things, looks about right" — and it means
a tuning change that quietly breaks underline detection fails here instead of in
someone's notes.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import pytest

from app.services.layout.detect import (
    Rect,
    find_grids,
    find_highlights,
    find_text_blocks,
    find_underlines,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
PAGE = FIXTURES / "structured_page.png"
TRUTH = FIXTURES / "structured_page_truth.json"


@pytest.fixture(scope="module")
def page():
    if not PAGE.exists():
        pytest.skip("run: python fixtures/make_structured_page.py")
    return cv2.imread(str(PAGE))


@pytest.fixture(scope="module")
def truth() -> dict[str, list[int]]:
    return json.loads(TRUTH.read_text(encoding="utf-8"))


def iou(a: Rect, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    left, top = max(ax, bx), max(ay, by)
    right, bottom = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    if right <= left or bottom <= top:
        return 0.0
    overlap = (right - left) * (bottom - top)
    return overlap / (aw * ah + bw * bh - overlap)


# --------------------------------------------------------------------------
# Grids: tables and boxes
# --------------------------------------------------------------------------


def test_table_is_found_with_the_right_shape(page, truth):
    tables = [grid for grid in find_grids(page) if grid.is_table]

    assert len(tables) == 1
    assert iou(tables[0].rect, truth["table"]) > 0.9
    assert (tables[0].rows, tables[0].columns) == (4, 3)


def test_a_drawn_box_is_not_reported_as_a_table(page, truth):
    """A box is a one-cell grid. Calling it a table would put an empty 1x1
    spreadsheet in the user's document."""
    boxes = [grid for grid in find_grids(page) if not grid.is_table]

    assert len(boxes) == 1
    assert iou(boxes[0].rect, truth["box"]) > 0.85
    assert (boxes[0].rows, boxes[0].columns) == (1, 1)


def test_the_table_and_the_box_stay_separate(page):
    """Regression: they share a left margin, and alignment is not connection.
    Grouping by coordinate alignment merged them into one six-row table."""
    grids = find_grids(page)

    assert len(grids) == 2
    assert grids[0].rect[1] < grids[1].rect[1]


def test_table_cells_tile_the_table(page):
    table = next(grid for grid in find_grids(page) if grid.is_table)

    first = table.cell_rect(0, 0)
    last = table.cell_rect(table.rows - 1, table.columns - 1)

    assert first[0] == table.rect[0]
    assert first[1] == table.rect[1]
    assert last[0] + last[2] == table.rect[0] + table.rect[2]
    assert last[1] + last[3] == table.rect[1] + table.rect[3]


# --------------------------------------------------------------------------
# Annotations
# --------------------------------------------------------------------------


def test_underline_is_found_under_its_words(page, truth):
    underlines = find_underlines(page, find_grids(page))

    assert len(underlines) == 1
    assert iou(underlines[0], truth["underline"]) > 0.85


def test_underline_does_not_absorb_table_rules(page):
    """Table rules are horizontal lines too — only grid membership tells them
    apart, and there are five of them in this page's table alone."""
    grids = find_grids(page)
    table = next(grid for grid in grids if grid.is_table)

    for rect in find_underlines(page, grids):
        assert not (table.rect[1] <= rect[1] <= table.rect[1] + table.rect[3])


def test_underline_length_matches_the_phrase(page, truth):
    """Morphology that closes gaps must not stretch the line: an underline
    reported wider than its words looks like a detection error to the user."""
    underline = find_underlines(page, find_grids(page))[0]

    assert underline[2] == pytest.approx(truth["underline"][2], abs=15)


def test_highlight_is_found_with_its_colour(page, truth):
    highlights = find_highlights(page)

    assert len(highlights) == 1
    rect, color = highlights[0]
    assert iou(rect, truth["highlight"]) > 0.9
    # Median, not mean: the dark text on top must not drag the colour to grey.
    assert color.lower() == "#ffe25c"


def test_plain_ink_is_not_mistaken_for_a_highlight(page):
    """The page is mostly dark text on near-white paper; only one thing on it
    is saturated."""
    assert len(find_highlights(page)) == 1


# --------------------------------------------------------------------------
# Text blocks
# --------------------------------------------------------------------------


def test_text_blocks_skip_table_cell_contents(page):
    grids = find_grids(page)
    tables = [grid for grid in grids if grid.is_table]
    table = tables[0]

    for block in find_text_blocks(page, exclude=tables):
        x, y, w, h = block.rect
        center_y = y + h / 2
        inside_table = table.rect[1] <= center_y <= table.rect[1] + table.rect[3]
        assert not inside_table, f"table cell text leaked out as a block: {block.rect}"


def test_boxed_text_survives_as_a_block(page, truth):
    """Text inside a drawn box is a real paragraph that happens to be boxed.
    Only tables are excluded, because their text belongs to cells."""
    tables = [grid for grid in find_grids(page) if grid.is_table]
    box = truth["box"]

    blocks = find_text_blocks(page, exclude=tables)
    inside_box = [
        block
        for block in blocks
        if box[1] <= block.rect[1] + block.rect[3] / 2 <= box[1] + box[3]
    ]

    assert len(inside_box) == 1


def test_line_height_distinguishes_a_heading_from_a_tall_paragraph(page):
    """The regression this guards: the closing two-line paragraph is taller
    than the one-line title, so comparing block heights calls it a heading."""
    tables = [grid for grid in find_grids(page) if grid.is_table]
    blocks = find_text_blocks(page, exclude=tables)

    title = blocks[0]
    multi_line = max(blocks, key=lambda block: block.line_count)

    assert title.line_count == 1
    assert multi_line.line_count >= 2
    assert multi_line.rect[3] > title.rect[3]  # taller overall...
    assert multi_line.line_height < title.line_height  # ...but smaller type
