"""Google Cloud Vision adapter — the Mode 1 default once credentials exist.

Status: wired, not yet verified against the live API. Phase 1's first task is to
point ``OCR_ENGINE=cloud_vision`` at a real key and check the mapping below
against a real response, then compare the overlay with the mock output.

Why Cloud Vision for Mode 1: ``document_text_detection`` returns bounding boxes
*and* recognized text in a single call, and handles rotated, skewed handwriting
far better than anything we could train in a semester. The first 1,000 images a
month are free, which covers all of development.
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool

from app.schemas.common import Point, Quad, TextRegion
from app.schemas.lens import LensResult
from app.services.images import read_image_size
from app.services.ocr.base import OcrEngine, OcrEngineError


class CloudVisionOcrEngine(OcrEngine):
    name = "cloud_vision"

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
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
                    "GOOGLE_APPLICATION_CREDENTIALS pointed at a valid service-account key?"
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
        regions: list[TextRegion] = []
        index = 0

        # NOTE (Phase 1): this produces WORD-level regions. Grouping words into
        # lines means walking symbol.property.detected_break for LINE_BREAK /
        # EOL_SURE_SPACE — worth doing, because selecting a whole line feels much
        # better than selecting word by word.
        for page in response.full_text_annotation.pages:
            for block in page.blocks:
                for paragraph in block.paragraphs:
                    for word in paragraph.words:
                        text = "".join(symbol.text for symbol in word.symbols)
                        vertices = word.bounding_box.vertices
                        if len(vertices) != 4:
                            continue
                        regions.append(
                            TextRegion(
                                id=f"cv-word-{index}",
                                text=text,
                                quad=Quad(points=[Point(x=v.x, y=v.y) for v in vertices]),
                                confidence=float(word.confidence or 0.0),
                                level="word",
                            )
                        )
                        index += 1

        return LensResult(
            image_width=width,
            image_height=height,
            regions=regions,
            full_text=response.full_text_annotation.text,
            engine=self._engine_info(started),
        )
