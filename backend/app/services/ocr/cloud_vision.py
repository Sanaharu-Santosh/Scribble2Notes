"""Google Cloud Vision adapter — the Mode 1 default.

Why Cloud Vision: ``document_text_detection`` returns bounding boxes *and*
recognized text in one call, and handles rotated, skewed handwriting far better
than anything trainable in a semester. The first 1,000 images a month are free.

The file is deliberately in two halves:

* :func:`extract_words` touches Google's response types and nothing else.
* :func:`group_into_lines` is pure — quads, text and confidences in, regions out.

That split is what makes the mapping testable without credentials: the tests feed
a hand-built response through the first and hand-built words through the second.
See ``tests/test_cloud_vision_mapping.py``, and ``docs/cloud-vision-setup.md``
for getting a key and capturing a real response to check against.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.schemas.common import Point, Quad, TextRegion
from app.schemas.lens import LensResult
from app.services.images import read_image_size
from app.services.ocr.base import OcrEngine, OcrEngineError

# TextAnnotation.DetectedBreak.BreakType values.
#
# Compared as plain integers rather than by importing the enum: the symbol field
# has been spelled both `type` and `type_` across google-cloud-vision releases,
# and the enum's import path has moved more than once. The numbers have not.
BREAK_SPACE = 1
BREAK_SURE_SPACE = 2
BREAK_EOL_SURE_SPACE = 3
BREAK_HYPHEN = 4
BREAK_LINE_BREAK = 5

SPACE_BREAKS = frozenset({BREAK_SPACE, BREAK_SURE_SPACE})
LINE_ENDING_BREAKS = frozenset({BREAK_EOL_SURE_SPACE, BREAK_HYPHEN, BREAK_LINE_BREAK})


@dataclass
class DetectedWord:
    """One word, plus what the engine said about what follows it."""

    text: str
    quad: Quad
    confidence: float
    trailing_space: bool = False
    ends_line: bool = False


def _break_type(symbol) -> int | None:
    """Read a symbol's break type across google-cloud-vision spellings."""
    prop = getattr(symbol, "property", None)
    detected = getattr(prop, "detected_break", None) if prop is not None else None
    if detected is None:
        return None
    value = getattr(detected, "type_", None)
    if value is None:
        value = getattr(detected, "type", None)
    return None if value is None else int(value)


def extract_words(response) -> list[DetectedWord]:
    """Walk a ``document_text_detection`` response down to word level."""
    words: list[DetectedWord] = []

    for page in response.full_text_annotation.pages:
        for block in page.blocks:
            for paragraph in block.paragraphs:
                paragraph_words: list[DetectedWord] = []

                for word in paragraph.words:
                    vertices = list(word.bounding_box.vertices)
                    if len(vertices) != 4:
                        continue

                    symbols = list(word.symbols)
                    # Google attaches a break to the symbol it follows, so a
                    # word's own trailing break lives on its last symbol.
                    trailing = _break_type(symbols[-1]) if symbols else None

                    paragraph_words.append(
                        DetectedWord(
                            text="".join(symbol.text for symbol in symbols),
                            quad=Quad(points=[Point(x=v.x, y=v.y) for v in vertices]),
                            confidence=float(getattr(word, "confidence", 0.0) or 0.0),
                            trailing_space=trailing in SPACE_BREAKS,
                            ends_line=trailing in LINE_ENDING_BREAKS,
                        )
                    )

                # A paragraph always ends a line, even if the response omitted
                # the break — otherwise one missing field merges two paragraphs
                # into a single unreadable region.
                if paragraph_words:
                    paragraph_words[-1].ends_line = True
                    paragraph_words[-1].trailing_space = False
                words.extend(paragraph_words)

    return words


def _union_quad(quads: list[Quad]) -> Quad:
    """Axis-aligned fallback. Loses slant, so only used when the merge fails."""
    xs = [point.x for quad in quads for point in quad.points]
    ys = [point.y for quad in quads for point in quad.points]
    return Quad.from_bbox(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def merge_line_quad(quads: list[Quad]) -> Quad:
    """Span from the first word's left edge to the last word's right edge.

    Built from the outer corners rather than a bounding box so the line keeps
    the slant of the writing — a bounding box around slanted words is taller
    than the text and would make the overlay font too big.
    """
    first, last = quads[0], quads[-1]
    if last.points[1].x <= first.points[0].x:
        # Words not in left-to-right order (RTL, or odd detection order).
        return _union_quad(quads)
    return Quad(points=[first.points[0], last.points[1], last.points[2], first.points[3]])


def group_into_lines(words: list[DetectedWord]) -> list[TextRegion]:
    """Collapse words into line regions, splitting where the engine said to."""
    regions: list[TextRegion] = []
    buffer: list[DetectedWord] = []

    def flush() -> None:
        if not buffer:
            return
        text = "".join(word.text + (" " if word.trailing_space else "") for word in buffer)
        regions.append(
            TextRegion(
                id=f"cv-line-{len(regions)}",
                text=text.strip(),
                quad=merge_line_quad([word.quad for word in buffer]),
                confidence=sum(word.confidence for word in buffer) / len(buffer),
                level="line",
            )
        )
        buffer.clear()

    for word in words:
        buffer.append(word)
        if word.ends_line:
            flush()
    flush()

    return regions


def as_word_regions(words: list[DetectedWord]) -> list[TextRegion]:
    """Raw detection granularity — one region per word, no grouping."""
    return [
        TextRegion(
            id=f"cv-word-{index}",
            text=word.text,
            quad=word.quad,
            confidence=word.confidence,
            level="word",
        )
        for index, word in enumerate(words)
    ]


def apply_credentials() -> None:
    """Make ``backend/.env``'s key path visible to the Google library.

    The library reads ``GOOGLE_APPLICATION_CREDENTIALS`` from the process
    environment and knows nothing about our ``.env`` file, so without this a
    perfectly correct-looking path in ``.env`` would silently do nothing.

    An existing environment variable always wins, and leaving the setting empty
    is the right choice when using ``gcloud auth application-default login`` —
    application default credentials are only consulted when this variable is
    *unset*. See docs/cloud-vision-setup.md.
    """
    key_path = get_settings().google_application_credentials
    if key_path and "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path


class CloudVisionOcrEngine(OcrEngine):
    name = "cloud_vision"

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            apply_credentials()
            try:
                from google.cloud import vision  # noqa: PLC0415
            except ImportError as exc:
                raise OcrEngineError(
                    "google-cloud-vision is not installed. "
                    "Run: pip install -r requirements-cloud.txt"
                ) from exc
            try:
                self._client = vision.ImageAnnotatorClient()
            except Exception as exc:  # credentials problems surface here
                raise OcrEngineError(
                    "Could not create a Cloud Vision client. Is "
                    "GOOGLE_APPLICATION_CREDENTIALS pointed at a valid "
                    "service-account key? See docs/cloud-vision-setup.md"
                ) from exc
        return self._client

    async def recognize(self, image: bytes) -> LensResult:
        from google.cloud import vision  # noqa: PLC0415

        started = self._now()
        client = self._get_client()
        request_image = vision.Image(content=image)

        # The Google client is synchronous; keep it off the event loop.
        response = await run_in_threadpool(client.document_text_detection, image=request_image)
        if response.error.message:
            raise OcrEngineError(f"Cloud Vision error: {response.error.message}")

        width, height = read_image_size(image)
        words = extract_words(response)
        granularity = get_settings().ocr_granularity
        regions = group_into_lines(words) if granularity == "line" else as_word_regions(words)

        return LensResult(
            image_width=width,
            image_height=height,
            regions=regions,
            full_text=response.full_text_annotation.text,
            engine=self._engine_info(started),
        )
