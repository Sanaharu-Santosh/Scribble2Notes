"""The one interface every Mode 1 engine implements.

This seam is the whole point of the architecture: the frontend and the API
routes only ever see :class:`OcrEngine`, so the thing that actually reads the
ink — a cloud API today, a self-hosted model tomorrow, your own retrained CRNN
eventually — can be swapped by changing one environment variable.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from app.schemas.common import EngineInfo
from app.schemas.lens import LensResult


class OcrEngineError(RuntimeError):
    """Raised when an engine is selected but cannot run (missing key, dep, etc.)."""


class OcrEngine(ABC):
    """Detects text regions in an image and recognizes what each one says."""

    name: str = "unnamed"
    is_mock: bool = False

    @abstractmethod
    async def recognize(self, image: bytes) -> LensResult:
        """Return every text region found, in source-image pixel coordinates."""

    # -- helpers for implementations -------------------------------------
    @staticmethod
    def _now() -> float:
        return time.perf_counter()

    def _engine_info(self, started_at: float) -> EngineInfo:
        return EngineInfo(
            name=self.name,
            duration_ms=int((self._now() - started_at) * 1000),
            is_mock=self.is_mock,
        )
