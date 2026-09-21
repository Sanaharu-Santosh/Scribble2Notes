from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import get_settings
from app.main import create_app
from app.services.layout.registry import get_layout_engine
from app.services.ocr.registry import get_ocr_engine

PAGE_WIDTH = 1200
PAGE_HEIGHT = 1600


def _clear_caches() -> None:
    get_settings.cache_clear()
    get_ocr_engine.cache_clear()
    get_layout_engine.cache_clear()


@pytest.fixture(autouse=True)
def hermetic_settings(monkeypatch):
    """Pin the engines for every test.

    Without this, the suite would start failing the moment someone puts a real
    ``OCR_ENGINE`` in their local ``backend/.env`` — a confusing failure that has
    nothing to do with the code under test. Tests that need other values call
    :func:`use_settings`.
    """
    monkeypatch.setenv("OCR_ENGINE", "mock")
    monkeypatch.setenv("LAYOUT_ENGINE", "mock")
    monkeypatch.setenv("OCR_GRANULARITY", "line")
    _clear_caches()
    yield
    _clear_caches()


def use_settings(monkeypatch, **overrides: str) -> None:
    """Override settings for one test, clearing the caches that hold them."""
    for key, value in overrides.items():
        monkeypatch.setenv(key.upper(), str(value))
    _clear_caches()


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def page_image() -> bytes:
    """A blank page-shaped PNG. The mock engines scale their output to it."""
    buffer = io.BytesIO()
    Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def upload(image: bytes) -> dict:
    return {"file": ("page.png", image, "image/png")}
