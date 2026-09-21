"""Generate a page that actually has structure, plus ground truth for it.

``sample-note.png`` is ruled lines and text — enough for Mode 1, useless for
Mode 2, which is about tables, boxes, underlines and highlights. This draws a
page containing all of them and writes down exactly where it put them, so the
OpenCV annotation pass can be tested against known answers instead of eyeballed.

Run from backend/:  python fixtures/make_structured_page.py
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1240, 1754
MARGIN = 100
CONTENT_RIGHT = WIDTH - MARGIN

PAPER = (252, 251, 247)
INK = (28, 36, 54)
RULE = (120, 132, 148)
UNDERLINE = (24, 28, 40)
HIGHLIGHT = (255, 226, 92)
BOX = (40, 48, 70)

FONT_CANDIDATES = {
    "body": [
        "/usr/share/fonts/truetype/crosextra/Caladea-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    ],
    "bold": [
        "/usr/share/fonts/truetype/crosextra/Caladea-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    ],
}

OUTPUT_IMAGE = Path(__file__).resolve().parent / "structured_page.png"
OUTPUT_TRUTH = Path(__file__).resolve().parent / "structured_page_truth.json"

TABLE_ROWS = [
    ["Region", "Comes from", "Becomes"],
    ["Paragraph", "layout model", "text box"],
    ["Table", "table model", "real grid"],
    ["Underline", "our CV pass", "vector stroke"],
]


def load_font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES[kind]:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default(size)


def text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    return right - left


def main() -> None:
    page = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(page)
    truth: dict[str, list[int]] = {}

    title_font = load_font("bold", 46)
    body_font = load_font("body", 34)
    cell_font = load_font("body", 30)

    draw.text((MARGIN, 110), "Unit 4 - Layout analysis", font=title_font, fill=INK)

    # --- paragraph with an underlined phrase -----------------------------
    draw.text((MARGIN, 210), "A page is not a flat list of words. It has", font=body_font, fill=INK)

    line_y = 265
    prefix, target, suffix = "structure: ", "tables, boxes and underlines", ", which"
    prefix_width = text_width(draw, prefix, body_font)
    target_width = text_width(draw, target, body_font)

    draw.text((MARGIN, line_y), prefix + target + suffix, font=body_font, fill=INK)
    underline_y = line_y + 46
    draw.rectangle(
        [MARGIN + prefix_width, underline_y, MARGIN + prefix_width + target_width, underline_y + 4],
        fill=UNDERLINE,
    )
    truth["underline"] = [MARGIN + prefix_width, underline_y, target_width, 5]

    # --- line with a highlighted phrase ----------------------------------
    highlight_line_y = 330
    prefix2, target2 = "each become ", "a different editable object"
    prefix2_width = text_width(draw, prefix2, body_font)
    target2_width = text_width(draw, target2, body_font)

    # Drawn before the text so the ink sits on top of the marker, as it would
    # on paper.
    highlight_box = [
        MARGIN + prefix2_width - 6,
        highlight_line_y - 4,
        MARGIN + prefix2_width + target2_width + 6,
        highlight_line_y + 44,
    ]
    draw.rectangle(highlight_box, fill=HIGHLIGHT)
    draw.text((MARGIN, highlight_line_y), prefix2 + target2 + ".", font=body_font, fill=INK)
    truth["highlight"] = [
        highlight_box[0],
        highlight_box[1],
        highlight_box[2] - highlight_box[0],
        highlight_box[3] - highlight_box[1],
    ]

    # --- table ------------------------------------------------------------
    table_top = 450
    row_height = 95
    table_bottom = table_top + row_height * len(TABLE_ROWS)
    column_edges = [MARGIN, 440, 800, CONTENT_RIGHT]

    for index in range(len(TABLE_ROWS) + 1):
        y = table_top + index * row_height
        draw.line([(MARGIN, y), (CONTENT_RIGHT, y)], fill=RULE, width=3)
    for x in column_edges:
        draw.line([(x, table_top), (x, table_bottom)], fill=RULE, width=3)

    for row_index, row in enumerate(TABLE_ROWS):
        font = load_font("bold", 30) if row_index == 0 else cell_font
        for column_index, value in enumerate(row):
            draw.text(
                (column_edges[column_index] + 18, table_top + row_index * row_height + 28),
                value,
                font=font,
                fill=INK,
            )

    truth["table"] = [MARGIN, table_top, CONTENT_RIGHT - MARGIN, table_bottom - table_top]

    # --- boxed formula ----------------------------------------------------
    box = [MARGIN, table_bottom + 90, MARGIN + 520, table_bottom + 230]
    draw.rectangle(box, outline=BOX, width=4)
    draw.text((box[0] + 30, box[1] + 45), "CER = edits / chars", font=body_font, fill=INK)
    truth["box"] = [box[0], box[1], box[2] - box[0], box[3] - box[1]]

    # --- closing paragraph -------------------------------------------------
    draw.text(
        (MARGIN, box[3] + 90),
        "No layout model reports underlines or highlights,",
        font=body_font,
        fill=INK,
    )
    draw.text(
        (MARGIN, box[3] + 145),
        "so we detect those ourselves and attach them.",
        font=body_font,
        fill=INK,
    )

    page.save(OUTPUT_IMAGE, format="PNG", optimize=True)
    OUTPUT_TRUTH.write_text(json.dumps(truth, indent=2), encoding="utf-8")

    print(f"wrote {OUTPUT_IMAGE.name} ({OUTPUT_IMAGE.stat().st_size // 1024} KB)")
    print(f"wrote {OUTPUT_TRUTH.name}: {json.dumps(truth)}")


if __name__ == "__main__":
    main()
