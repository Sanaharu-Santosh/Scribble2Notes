"""A deterministic stand-in for a real OCR engine.

Why this exists: it lets the whole app — upload, detect, overlay, select, copy —
run end to end on day one with no API keys, no credit card and no GPU. Phase 1
then becomes "point the registry at a real engine and compare", rather than
"build everything at once and hope".

It lays plausible text lines over *whatever* image you upload, scaled to that
image's dimensions and with a slight per-line slant, so the frontend's rotation
and scaling maths get exercised properly rather than only against tidy
axis-aligned rectangles.
"""

from __future__ import annotations

from app.schemas.common import TextRegion
from app.schemas.lens import LensResult
from app.services.images import read_image_size, slanted_quad
from app.services.ocr.base import OcrEngine

SAMPLE_LINES = [
    "Lecture 7 - Sequence models",
    "CTC solves the alignment problem:",
    "input pixels and output characters are",
    "not aligned, so sum over every valid",
    "alignment instead of picking just one.",
    "ref: Graves et al. 2006",
]


class MockOcrEngine(OcrEngine):
    name = "mock"
    is_mock = True

    async def recognize(self, image: bytes) -> LensResult:
        started = self._now()
        width, height = read_image_size(image)

        left = width * 0.08
        usable_width = width * 0.84
        line_height = height * 0.052
        step = height * 0.085
        top = height * 0.10

        longest = max(len(line) for line in SAMPLE_LINES)
        regions: list[TextRegion] = []

        for index, line in enumerate(SAMPLE_LINES):
            # Deterministic so tests and screenshots stay stable between runs.
            angle = ((index * 37) % 7 - 3) * 0.4
            confidence = 0.82 + ((index * 13) % 15) / 100
            line_width = usable_width * (len(line) / longest)

            regions.append(
                TextRegion(
                    id=f"mock-line-{index}",
                    text=line,
                    quad=slanted_quad(left, top + index * step, line_width, line_height, angle),
                    confidence=round(confidence, 2),
                    level="line",
                )
            )

        return LensResult(
            image_width=width,
            image_height=height,
            regions=regions,
            full_text="\n".join(SAMPLE_LINES),
            engine=self._engine_info(started),
        )
