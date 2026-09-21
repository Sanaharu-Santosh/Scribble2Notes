"""Replay a saved response instead of calling a live API.

Why this exists: once you have a real Cloud Vision response for a page, you can
iterate on the overlay, the styling and the selection behaviour for hours
without spending quota, needing a network, or waiting on a round trip — while
still working against *real* engine output rather than the mock's tidy lines.

Capture one with::

    python scripts/try_engine.py --image page.png --engine cloud_vision --save-fixture

then set ``OCR_ENGINE=fixture`` in ``backend/.env``.

A fixture is tied to the image it was captured from. If you upload a different
size of the same image, coordinates are scaled to fit; upload a genuinely
different page and the overlay will be visibly wrong, which is the honest
outcome — it is replaying a recording, not reading your image.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.config import get_settings
from app.schemas.common import EngineInfo, TextRegion
from app.schemas.lens import LensResult
from app.services.images import read_image_size, scale_quad
from app.services.ocr.base import OcrEngine, OcrEngineError


class FixtureOcrEngine(OcrEngine):
    name = "fixture"
    is_mock = True

    async def recognize(self, image: bytes) -> LensResult:
        started = self._now()
        settings = get_settings()

        path = Path(settings.ocr_fixture_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            raise OcrEngineError(
                f"No fixture at {path}. Capture one with: "
                "python scripts/try_engine.py --image page.png "
                "--engine cloud_vision --save-fixture"
            )

        try:
            saved = LensResult.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValueError) as exc:
            raise OcrEngineError(f"Fixture at {path} is not a valid LensResult: {exc}") from exc

        width, height = read_image_size(image)
        regions = saved.regions

        if (width, height) != (saved.image_width, saved.image_height):
            scale_x = width / saved.image_width
            scale_y = height / saved.image_height
            regions = [
                TextRegion(
                    id=region.id,
                    text=region.text,
                    quad=scale_quad(region.quad, scale_x, scale_y),
                    confidence=region.confidence,
                    level=region.level,
                )
                for region in saved.regions
            ]

        return LensResult(
            image_width=width,
            image_height=height,
            regions=regions,
            full_text=saved.full_text,
            engine=EngineInfo(
                # Name the engine the recording came from, so the UI can never
                # imply a live call happened.
                name=f"fixture<{saved.engine.name}>",
                duration_ms=int((self._now() - started) * 1000),
                is_mock=True,
            ),
        )
