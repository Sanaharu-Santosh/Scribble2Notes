"""Classical CV detection of the structure a notes page actually has.

Deliberately model-free. Two reasons:

1. Ruled tables, drawn boxes, underlines and highlighter marks are *lines and
   colour*. Morphology finds them exactly, in milliseconds, on a CPU, with no
   weights to download — where a document model trained on printed PDFs is both
   heavier and less reliable on a page someone ruled with a pen.
2. Nothing else reports underlines or highlights at all. Those were always going
   to be ours to write (see docs/architecture.md), and once you are extracting
   horizontal lines for underlines, table rules and box edges come free from the
   same pass.

Every function here takes a BGR image as a numpy array and returns plain pixel
rectangles. Nothing in this module imports our schemas, so it can be tested as
straight image processing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

# A "long" line is one spanning at least this fraction of the page width. Used
# to size the morphology kernels, not as a classification threshold.
LINE_KERNEL_FRACTION = 0.035
MIN_LINE_LENGTH_FRACTION = 0.06

# Highlighter ink is saturated; paper and pen are not.
HIGHLIGHT_MIN_SATURATION = 70
HIGHLIGHT_MIN_VALUE = 110
HIGHLIGHT_MIN_AREA_FRACTION = 0.0004

Rect = tuple[int, int, int, int]  # x, y, width, height


@dataclass
class Grid:
    """A rectangle ruled by lines — a table if it has cells, a box if it doesn't."""

    rect: Rect
    row_edges: list[int] = field(default_factory=list)
    column_edges: list[int] = field(default_factory=list)

    @property
    def rows(self) -> int:
        return max(len(self.row_edges) - 1, 0)

    @property
    def columns(self) -> int:
        return max(len(self.column_edges) - 1, 0)

    @property
    def is_table(self) -> bool:
        """More than one cell in some direction. A lone cell is a drawn box."""
        return self.rows * self.columns > 1

    def cell_rect(self, row: int, column: int) -> Rect:
        top, bottom = self.row_edges[row], self.row_edges[row + 1]
        left, right = self.column_edges[column], self.column_edges[column + 1]
        return (left, top, right - left, bottom - top)


def to_ink_mask(image: np.ndarray) -> np.ndarray:
    """White ink on black background — the convention every step below expects."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Otsu rather than a fixed threshold: a photographed page is never the same
    # brightness twice.
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    return binary


def _extract_lines(mask: np.ndarray, horizontal: bool) -> np.ndarray:
    length = max(int(mask.shape[1] * LINE_KERNEL_FRACTION), 10)
    size = (length, 1) if horizontal else (1, length)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, size)
    opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    # Close small gaps so a hand-ruled line that skips doesn't become two lines.
    # Closing rather than dilation: dilation would stretch every line by the
    # kernel length, which shows up later as underlines wider than the words
    # they sit under.
    gap_size = (max(length // 3, 3), 1) if horizontal else (1, max(length // 3, 3))
    gap_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, gap_size)
    return cv2.morphologyEx(opened, cv2.MORPH_CLOSE, gap_kernel, iterations=1)


def _segments(line_mask: np.ndarray, horizontal: bool, min_length: int) -> list[Rect]:
    contours, _ = cv2.findContours(line_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    segments: list[Rect] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        span = w if horizontal else h
        thickness = h if horizontal else w
        # A line is long and thin; anything else is a glyph that survived opening.
        if span >= min_length and thickness <= max(span * 0.2, 12):
            segments.append((x, y, w, h))
    return segments


def _cluster(values: list[int], tolerance: int) -> list[int]:
    """Collapse near-identical coordinates into one edge each."""
    if not values:
        return []
    ordered = sorted(values)
    clusters = [[ordered[0]]]
    for value in ordered[1:]:
        if value - clusters[-1][-1] <= tolerance:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [int(round(sum(group) / len(group))) for group in clusters]


def find_grids(image: np.ndarray) -> list[Grid]:
    """Find every rectangle ruled by crossing lines: tables and drawn boxes."""
    mask = to_ink_mask(image)
    height, width = mask.shape
    min_length = int(width * MIN_LINE_LENGTH_FRACTION)

    horizontal = _extract_lines(mask, horizontal=True)
    vertical = _extract_lines(mask, horizontal=False)

    if not _segments(horizontal, True, min_length):
        return []

    # One connected blob of ruling per ruled rectangle. A table's rules all
    # touch each other; a separate box below it touches nothing of the table's,
    # so they come out as two components.
    #
    # Clustering the crossing points instead would merge them: a box sharing a
    # left margin with the table two hundred pixels above is "column-aligned"
    # with it, and alignment is not connection.
    ruling = cv2.bitwise_or(horizontal, vertical)
    crossing_mask = cv2.dilate(
        cv2.bitwise_and(horizontal, vertical),
        cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)),
    )
    tolerance = max(int(height * 0.012), 8)

    grids: list[Grid] = []
    components, _ = cv2.findContours(ruling, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for component in components:
        cx, cy, cw, ch = cv2.boundingRect(component)
        if cw < min_length or ch < min_length // 2:
            continue

        window = crossing_mask[cy : cy + ch, cx : cx + cw]
        crossings, _ = cv2.findContours(window, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        points = []
        for crossing in crossings:
            x, y, w, h = cv2.boundingRect(crossing)
            points.append((cx + x + w // 2, cy + y + h // 2))
        if len(points) < 4:
            continue

        column_edges = _cluster([p[0] for p in points], tolerance)
        row_edges = _cluster([p[1] for p in points], tolerance)
        if len(column_edges) < 2 or len(row_edges) < 2:
            continue

        rect = (
            column_edges[0],
            row_edges[0],
            column_edges[-1] - column_edges[0],
            row_edges[-1] - row_edges[0],
        )
        grids.append(Grid(rect=rect, row_edges=row_edges, column_edges=column_edges))

    return sorted(grids, key=lambda grid: (grid.rect[1], grid.rect[0]))


def _inside_any(x: int, y: int, w: int, h: int, grids: list[Grid], padding: int = 12) -> bool:
    for grid in grids:
        gx, gy, gw, gh = grid.rect
        if (
            x >= gx - padding
            and y >= gy - padding
            and x + w <= gx + gw + padding
            and y + h <= gy + gh + padding
        ):
            return True
    return False


def _covered_fraction(rect: Rect, grids: list[Grid]) -> float:
    """How much of ``rect`` lies inside some grid, by area.

    A fraction beats an inside/outside test here: detected boxes are a pixel or
    two off the drawn ones, so a strict containment check keeps every table cell's
    text as a stray paragraph, while a generous padding swallows real paragraphs
    that merely sit near a table.
    """
    x, y, w, h = rect
    area = max(w * h, 1)
    covered = 0
    for grid in grids:
        gx, gy, gw, gh = grid.rect
        overlap_w = min(x + w, gx + gw) - max(x, gx)
        overlap_h = min(y + h, gy + gh) - max(y, gy)
        if overlap_w > 0 and overlap_h > 0:
            covered += overlap_w * overlap_h
    return min(covered / area, 1.0)


def find_underlines(image: np.ndarray, grids: list[Grid]) -> list[Rect]:
    """Horizontal strokes that rule text rather than a table.

    A line qualifies when it isn't part of any grid and there is ink directly
    above it — that "ink above" test is what separates an underline from a
    divider rule or an underexposed edge.
    """
    mask = to_ink_mask(image)
    height, width = mask.shape
    horizontal = _extract_lines(mask, horizontal=True)
    candidates = _segments(horizontal, True, int(width * MIN_LINE_LENGTH_FRACTION))

    underlines: list[Rect] = []
    for x, y, w, h in candidates:
        if h > max(height * 0.008, 8):
            continue  # too thick to be a pen underline
        if _inside_any(x, y, w, h, grids):
            continue

        band_height = max(int(h * 12), 20)
        top = max(y - band_height, 0)
        band = mask[top:y, x : x + w]
        if band.size == 0:
            continue
        ink_ratio = float(np.count_nonzero(band)) / band.size
        if ink_ratio < 0.02:
            continue  # nothing above it — a rule, not an underline

        underlines.append((x, y, w, h))

    return sorted(underlines, key=lambda rect: (rect[1], rect[0]))


def find_highlights(image: np.ndarray) -> list[tuple[Rect, str]]:
    """Saturated marker colour behind text. Returns rectangles and hex colours."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation, value = hsv[:, :, 1], hsv[:, :, 2]
    mask = ((saturation >= HIGHLIGHT_MIN_SATURATION) & (value >= HIGHLIGHT_MIN_VALUE)).astype(
        np.uint8
    ) * 255

    # Text sitting on the marker punches holes in the mask; close them so one
    # highlighted phrase is one rectangle rather than a dozen fragments.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 9))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    height, width = mask.shape
    min_area = height * width * HIGHLIGHT_MIN_AREA_FRACTION

    found: list[tuple[Rect, str]] = []
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        if cv2.contourArea(contour) < min_area:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        patch = image[y : y + h, x : x + w].reshape(-1, 3)
        # Median over the patch, so the dark text on top doesn't drag the
        # reported colour toward black.
        blue, green, red = np.median(patch, axis=0).astype(int)
        found.append(((x, y, w, h), f"#{red:02x}{green:02x}{blue:02x}"))

    return sorted(found, key=lambda item: (item[0][1], item[0][0]))


@dataclass
class TextBlock:
    rect: Rect
    line_count: int

    @property
    def line_height(self) -> float:
        """Height of one text line — the usable signal for heading detection.

        Block height is not: a two-line paragraph is taller than a one-line
        heading, so comparing block heights marks paragraphs as headings.
        """
        return self.rect[3] / max(self.line_count, 1)


def find_text_blocks(image: np.ndarray, exclude: list[Grid]) -> list[TextBlock]:
    """Group glyphs into paragraph-sized regions, skipping ruled areas.

    ``exclude`` should be the *tables* only. Text inside a drawn box is a real
    paragraph that happens to be boxed, and dropping it would lose the content;
    text inside a table belongs to its cells and would otherwise be reported
    twice.
    """
    mask = to_ink_mask(image)
    height, width = mask.shape

    # Remove the ruling so table rules don't glue every row into one blob. The
    # ruling mask is grown slightly first: subtracting it exactly leaves the
    # anti-aliased edges and line crossings behind, and those survive as tiny
    # phantom "paragraphs" hugging the table.
    lines = cv2.bitwise_or(_extract_lines(mask, True), _extract_lines(mask, False))
    lines = cv2.dilate(lines, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)), iterations=1)
    text_only = cv2.subtract(mask, lines)

    # Smear horizontally to join words into lines, then a little vertically to
    # join lines into paragraphs.
    wide = cv2.getStructuringElement(cv2.MORPH_RECT, (max(int(width * 0.02), 12), 3))
    mask_lines = cv2.dilate(text_only, wide, iterations=2)
    tall = cv2.getStructuringElement(cv2.MORPH_RECT, (5, max(int(height * 0.012), 8)))
    blocks_mask = cv2.dilate(mask_lines, tall, iterations=1)

    min_area = height * width * 0.0006
    line_contours, _ = cv2.findContours(mask_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    line_boxes = [cv2.boundingRect(contour) for contour in line_contours]

    blocks: list[TextBlock] = []
    contours, _ = cv2.findContours(blocks_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w * h < min_area:
            continue
        if _covered_fraction((x, y, w, h), exclude) > 0.6:
            continue  # this is a table cell's text, not a paragraph

        lines_inside = sum(
            1
            for lx, ly, lw, lh in line_boxes
            if lx >= x - 2 and ly >= y - 2 and lx + lw <= x + w + 2 and ly + lh <= y + h + 2
        )
        blocks.append(TextBlock(rect=(x, y, w, h), line_count=max(lines_inside, 1)))

    return sorted(blocks, key=lambda block: (block.rect[1], block.rect[0]))
