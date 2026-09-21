"""Picks the Mode 2 engine named by ``LAYOUT_ENGINE``."""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from app.config import get_settings
from app.services.layout.azure import AzureLayoutEngine
from app.services.layout.base import LayoutEngine, LayoutEngineError
from app.services.layout.mock import MockLayoutEngine
from app.services.layout.opencv_engine import OpenCvLayoutEngine
from app.services.layout.ppstructure import PPStructureLayoutEngine

ENGINES: dict[str, Callable[[], LayoutEngine]] = {
    "mock": MockLayoutEngine,
    "opencv": OpenCvLayoutEngine,
    "ppstructure": PPStructureLayoutEngine,
    "azure": AzureLayoutEngine,
}


@lru_cache
def get_layout_engine() -> LayoutEngine:
    name = get_settings().layout_engine
    factory = ENGINES.get(name)
    if factory is None:
        raise LayoutEngineError(f"Unknown LAYOUT_ENGINE {name!r}. Options: {', '.join(ENGINES)}")
    return factory()
