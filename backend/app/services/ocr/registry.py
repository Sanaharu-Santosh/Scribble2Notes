"""Picks the Mode 1 engine named by ``OCR_ENGINE``.

Cached, so a heavy engine (PaddleOCR loads model weights on construction) is
built once per process rather than once per request.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from app.config import get_settings
from app.services.ocr.base import OcrEngine, OcrEngineError
from app.services.ocr.cloud_vision import CloudVisionOcrEngine
from app.services.ocr.mock import MockOcrEngine
from app.services.ocr.paddle import PaddleOcrEngine

ENGINES: dict[str, Callable[[], OcrEngine]] = {
    "mock": MockOcrEngine,
    "cloud_vision": CloudVisionOcrEngine,
    "paddle": PaddleOcrEngine,
}


@lru_cache
def get_ocr_engine() -> OcrEngine:
    name = get_settings().ocr_engine
    factory = ENGINES.get(name)
    if factory is None:
        raise OcrEngineError(f"Unknown OCR_ENGINE {name!r}. Options: {', '.join(ENGINES)}")
    return factory()
