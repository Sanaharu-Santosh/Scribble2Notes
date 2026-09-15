"""The one interface every Mode 2 engine implements.

Same idea as :mod:`app.services.ocr.base`, but for document structure: an
implementation takes a page image and returns typed, placed blocks that the
canvas editor can turn into editable objects.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from app.schemas.common import EngineInfo
from app.schemas.scan import DocumentStructure


class LayoutEngineError(RuntimeError):
    """Raised when an engine is selected but cannot run (missing key, dep, etc.)."""


class LayoutEngine(ABC):
    """Decomposes a page into typed regions: paragraphs, tables, figures."""

    name: str = "unnamed"
    is_mock: bool = False

    @abstractmethod
    async def analyze(self, image: bytes) -> DocumentStructure:
        """Return the page's blocks in reading order, in pixel coordinates."""

    @staticmethod
    def _now() -> float:
        return time.perf_counter()

    def _engine_info(self, started_at: float) -> EngineInfo:
        return EngineInfo(
            name=self.name,
            duration_ms=int((self._now() - started_at) * 1000),
            is_mock=self.is_mock,
        )
