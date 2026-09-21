"""Scene -> PDF, keeping the layout and the text.

Where the DOCX export throws positions away for flow, this keeps them: the PDF
should look like the page the user was editing. It is built as absolutely
positioned HTML and rendered by WeasyPrint, which means the text in the result
is **real text** — selectable, searchable, copyable — rather than a screenshot
of a canvas. That distinction is the whole reason not to just export a PNG.

Scale: scanned pages here are ~150dpi and PDF works in points (1/72"), so
``px * 72/150`` maps a 1240x1754 scan onto exactly A4.
"""

from __future__ import annotations

import html
import math
import re

from weasyprint import HTML

from app.schemas.export import ExportDocument, ExportItem, ExportMark, ItemKind

PT_PER_PX = 72 / 150

# Colours arrive from the canvas, which means from the user. They are written
# into style attributes, so anything that isn't plainly a colour is dropped
# rather than escaped — there is no legitimate colour containing a semicolon.
SAFE_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$|^[a-zA-Z]{3,20}$")

DEFAULT_INK = "#1a2233"

STYLESHEET = """
@page {{ size: {width}pt {height}pt; margin: 0; }}
html, body {{ margin: 0; padding: 0; }}
body {{
  position: relative;
  width: {width}pt;
  height: {height}pt;
  font-family: "DejaVu Serif", Georgia, serif;
  color: {ink};
}}
.item {{ position: absolute; }}
.text {{ line-height: 1.25; white-space: pre-wrap; word-wrap: break-word; }}
.cell {{ border: 0.75pt solid {ink}; box-sizing: border-box; padding: 2pt 4pt;
         font-size: 9pt; overflow: hidden; }}
.figure {{ border: 0.75pt dashed #8a93a0; box-sizing: border-box; }}
.mark-highlight {{ opacity: 0.45; }}
.mark-box {{ border: 1pt solid {ink}; box-sizing: border-box; background: transparent; }}
"""


def safe_color(color: str | None, fallback: str = DEFAULT_INK) -> str:
    if color and SAFE_COLOR.match(color.strip()):
        return color.strip()
    return fallback


def pt(value: float) -> str:
    return f"{value * PT_PER_PX:.2f}pt"


def _position(item: ExportItem | ExportMark) -> str:
    return (
        f"left:{pt(item.x)};top:{pt(item.y)};"
        f"width:{pt(item.width)};height:{pt(item.height)}"
    )


def _text_html(item: ExportItem) -> str:
    text = html.escape(item.text or "")
    if not text.strip():
        return ""

    size = item.font_size or (28 if item.kind is ItemKind.HEADING else 18)
    weight = "bold" if item.kind is ItemKind.HEADING else "normal"
    underline = "underline" if any(mark.kind == "underline" for mark in item.marks) else "none"

    style = (
        f"{_position(item)};height:auto;"
        f"font-size:{pt(size)};font-weight:{weight};"
        f"color:{safe_color(item.color)};text-decoration:{underline}"
    )
    return f'<div class="item text" style="{style}">{text}</div>'


def _table_html(item: ExportItem) -> str:
    if not item.table or not item.table.cells:
        return ""

    # Cells are placed individually rather than as an HTML <table>: the point of
    # this export is that the page looks like what the user arranged, and they
    # may well have dragged a cell out of line.
    column_width = item.width / max(item.table.cols, 1)
    row_height = item.height / max(item.table.rows, 1)

    parts = []
    for cell in item.table.cells:
        left = item.x + cell.col * column_width
        top = item.y + cell.row * row_height
        style = (
            f"left:{pt(left)};top:{pt(top)};"
            f"width:{pt(column_width)};height:{pt(row_height)}"
        )
        parts.append(f'<div class="item cell" style="{style}">{html.escape(cell.text)}</div>')
    return "".join(parts)


def _figure_html(item: ExportItem) -> str:
    style = _position(item)
    background = safe_color(item.background, "transparent")
    if background != "transparent":
        style += f";background:{background}"
    label = html.escape(item.text or "")
    return f'<div class="item figure" style="{style}">{label}</div>'


def _stroke_html(item: ExportItem) -> str:
    """Lines, arrows and freehand, as inline SVG so they stay vector."""
    points = item.points or []
    if len(points) < 2:
        return ""

    scaled = [(x * PT_PER_PX, y * PT_PER_PX) for x, y in points]
    xs = [p[0] for p in scaled]
    ys = [p[1] for p in scaled]
    pad = 2.0
    min_x, min_y = min(xs) - pad, min(ys) - pad
    width = max(max(xs) - min_x + pad, 1)
    height = max(max(ys) - min_y + pad, 1)

    local = [(x - min_x, y - min_y) for x, y in scaled]
    path = " ".join(f"{x:.2f},{y:.2f}" for x, y in local)
    color = safe_color(item.color)

    head = ""
    if item.kind is ItemKind.ARROW:
        # Drawn from the last segment rather than with an SVG marker, so the
        # arrowhead scales with the page instead of with the stroke width.
        (x1, y1), (x2, y2) = local[-2], local[-1]
        angle = math.atan2(y2 - y1, x2 - x1)
        size = 6.0
        for spread in (2.6, -2.6):
            hx = x2 - size * math.cos(angle + spread / 3)
            hy = y2 - size * math.sin(angle + spread / 3)
            head += f'<line x1="{x2:.2f}" y1="{y2:.2f}" x2="{hx:.2f}" y2="{hy:.2f}" />'

    style = f"left:{item.x * PT_PER_PX + min_x:.2f}pt;top:{item.y * PT_PER_PX + min_y:.2f}pt"
    return (
        f'<svg class="item" style="{style}" width="{width:.2f}pt" height="{height:.2f}pt" '
        f'viewBox="0 0 {width:.2f} {height:.2f}" '
        f'stroke="{color}" stroke-width="1.2" fill="none" stroke-linecap="round">'
        f'<polyline points="{path}" />{head}</svg>'
    )


def _mark_html(mark: ExportMark) -> str:
    if mark.kind == "highlight":
        color = safe_color(mark.color, "#ffe14d")
        style = f"{_position(mark)};background:{color}"
        return f'<div class="item mark-highlight" style="{style}"></div>'
    if mark.kind == "box":
        return f'<div class="item mark-box" style="{_position(mark)}"></div>'
    color = safe_color(mark.color)
    height = max(mark.height, 2)
    style = f"left:{pt(mark.x)};top:{pt(mark.y)};width:{pt(mark.width)};height:{pt(height)}"
    return f'<div class="item" style="{style};background:{color}"></div>'


def render_html(document: ExportDocument) -> str:
    """The HTML WeasyPrint renders. Separated out so tests can read it."""
    items = document.in_reading_order()

    # Document order is stacking order: highlights sit behind their words,
    # underlines and boxes on top of them — the same layering the marks have on
    # paper, and the same rule the canvas follows.
    highlights = [
        _mark_html(mark) for item in items for mark in item.marks if mark.kind == "highlight"
    ]
    body: list[str] = []
    overlays = [
        _mark_html(mark) for item in items for mark in item.marks if mark.kind != "highlight"
    ]

    for item in items:
        if item.kind is ItemKind.TABLE:
            body.append(_table_html(item))
        elif item.kind in {ItemKind.LINE, ItemKind.ARROW}:
            overlays.append(_stroke_html(item))
        elif item.kind is ItemKind.FIGURE:
            body.append(_figure_html(item))
        else:
            body.append(_text_html(item))

    stylesheet = STYLESHEET.format(
        width=document.page_width * PT_PER_PX,
        height=document.page_height * PT_PER_PX,
        ink=DEFAULT_INK,
    )
    title = html.escape(document.title or "Scribble2Notes export")

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{title}</title><style>{stylesheet}</style></head><body>"
        + "".join(highlights)
        + "".join(body)
        + "".join(overlays)
        + "</body></html>"
    )


def build_pdf(document: ExportDocument) -> bytes:
    return HTML(string=render_html(document)).write_pdf()
