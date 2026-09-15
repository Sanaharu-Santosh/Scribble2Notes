from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app

PAGE_WIDTH = 1200
PAGE_HEIGHT = 1600


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
