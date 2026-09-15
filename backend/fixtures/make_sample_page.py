"""Generate frontend/public/sample-note.png — the demo page the app offers on load.

The trick: it asks the mock OCR engine where it *will* claim text is, then draws
the text into exactly those quads. So the first thing you see on a fresh clone is
an overlay that lands perfectly on the ink, which makes it obvious when a real
engine later lands badly.

Run from backend/:  python fixtures/make_sample_page.py
"""

from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.ocr.mock import MockOcrEngine  # noqa: E402

WIDTH, HEIGHT = 1240, 1754  # A4-ish at 150dpi
PAPER = (252, 251, 247)
RULE = (214, 224, 233)
MARGIN_RULE = (214, 122, 116)
INK = (32, 42, 66)

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/crosextra/Caladea-Italic.ttf",
    "/usr/share/fonts/truetype/crosextra/Caladea-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
]

OUTPUT = Path(__file__).resolve().parents[2] / "frontend" / "public" / "sample-note.png"


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default(size)


def blank_page() -> Image.Image:
    page = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(page)

    step = HEIGHT * 0.085
    y = HEIGHT * 0.10
    while y < HEIGHT - step:
        line_y = y + HEIGHT * 0.052 + 6
        draw.line([(WIDTH * 0.06, line_y), (WIDTH * 0.94, line_y)], fill=RULE, width=2)
        y += step

    margin_x = WIDTH * 0.06
    draw.line([(margin_x, 0), (margin_x, HEIGHT)], fill=MARGIN_RULE, width=2)
    return page


def draw_into_quad(page: Image.Image, text: str, quad) -> None:
    """Render `text` so it fills `quad`, matching its size and slant."""
    target_width = max(int(quad.bbox.width), 1)
    target_height = max(int(quad.height), 1)

    font = load_font(96)
    left, top, right, bottom = font.getbbox(text)
    natural = Image.new("RGBA", (max(right - left, 1), max(bottom - top, 1)), (0, 0, 0, 0))
    ImageDraw.Draw(natural).text((-left, -top), text, font=font, fill=(*INK, 255))

    stretched = natural.resize((target_width, target_height), Image.LANCZOS)
    # PIL rotates counter-clockwise; our angles are clockwise-positive.
    rotated = stretched.rotate(-quad.angle_deg, expand=True, resample=Image.BICUBIC)
    page.paste(rotated, (int(quad.bbox.x), int(quad.bbox.y)), rotated)


async def main() -> None:
    page = blank_page()

    buffer = io.BytesIO()
    page.save(buffer, format="PNG")
    result = await MockOcrEngine().recognize(buffer.getvalue())

    for region in result.regions:
        draw_into_quad(page, region.text, region.quad)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    page.save(OUTPUT, format="PNG", optimize=True)
    print(f"wrote {OUTPUT} ({OUTPUT.stat().st_size // 1024} KB, {len(result.regions)} lines)")


if __name__ == "__main__":
    asyncio.run(main())
