"""Self-hosted PaddleOCR adapter — the no-cloud, no-per-call-cost option.

Status: wired, not yet verified. Expects the classic ``PaddleOCR.ocr()`` result
shape, ``[[[box_points], (text, confidence)], ...]``. PaddleOCR 3.x also offers
``.predict()`` with a dict result; if you install 3.x, check this mapping first.

Trade-off worth remembering: no API cost, but you run the server, and CPU
inference is slow (seconds per image). Fine for Mode 2 batch work, painful for
Mode 1's "feels instant" requirement unless you have a GPU.
"""

from __future__ import annotations

import io

from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.schemas.common import Point, Quad, TextRegion
from app.schemas.lens import LensResult
from app.services.ocr.base import OcrEngine, OcrEngineError


class PaddleOcrEngine(OcrEngine):
    name = "paddle"

    def __init__(self) -> None:
        self._reader = None

    def _get_reader(self):
        if self._reader is None:
            settings = get_settings()
            try:
                from paddleocr import PaddleOCR  # noqa: PLC0415
            except ImportError as exc:
                raise OcrEngineError(
                    "paddleocr is not installed. Run: pip install -r requirements-paddle.txt"
                ) from exc
            # Model weights download on first construction, so build it once.
            self._reader = PaddleOCR(
                use_angle_cls=True,
                lang=settings.paddle_lang,
                use_gpu=settings.paddle_use_gpu,
                show_log=False,
            )
        return self._reader

    async def recognize(self, image: bytes) -> LensResult:
        import numpy as np  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415

        started = self._now()
        reader = self._get_reader()

        with Image.open(io.BytesIO(image)) as opened:
            rgb = opened.convert("RGB")
            width, height = rgb.width, rgb.height
            array = np.array(rgb)

        raw = await run_in_threadpool(reader.ocr, array, cls=True)
        page = (raw or [None])[0] or []

        regions: list[TextRegion] = []
        for index, entry in enumerate(page):
            box, (text, confidence) = entry[0], entry[1]
            if len(box) != 4:
                continue
            regions.append(
                TextRegion(
                    id=f"paddle-line-{index}",
                    text=text,
                    quad=Quad(points=[Point(x=float(px), y=float(py)) for px, py in box]),
                    confidence=float(confidence),
                    level="line",
                )
            )

        return LensResult(
            image_width=width,
            image_height=height,
            regions=regions,
            full_text="\n".join(region.text for region in regions),
            engine=self._engine_info(started),
        )
