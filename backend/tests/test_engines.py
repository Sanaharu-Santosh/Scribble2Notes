"""Engine selection, granularity, and the fixture replay engine."""

from __future__ import annotations

import json
import os

import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.schemas.lens import LensResult
from app.services.ocr.base import OcrEngineError
from app.services.ocr.cloud_vision import apply_credentials
from app.services.ocr.registry import ENGINES, get_ocr_engine
from tests.conftest import PAGE_HEIGHT, PAGE_WIDTH, upload, use_settings


def test_unknown_engine_name_fails_at_startup(monkeypatch):
    """`create_app` builds Settings eagerly, so a typo'd OCR_ENGINE stops the
    server at boot with the valid options listed — rather than surfacing as a
    confusing 500 on the first upload."""
    use_settings(monkeypatch, ocr_engine="nope")

    with pytest.raises(ValidationError, match="'mock', 'fixture', 'cloud_vision' or 'paddle'"):
        get_settings()


def test_registry_catches_an_engine_that_was_never_registered(monkeypatch):
    """Guards the other half: a name added to the Literal but not to ENGINES."""
    monkeypatch.delitem(ENGINES, "mock")
    get_ocr_engine.cache_clear()

    with pytest.raises(OcrEngineError, match="Unknown OCR_ENGINE"):
        get_ocr_engine()


# --------------------------------------------------------------------------
# Granularity
# --------------------------------------------------------------------------


def test_line_granularity_is_the_default(client, page_image):
    body = client.post("/api/lens", files=upload(page_image)).json()
    assert {region["level"] for region in body["regions"]} == {"line"}


def test_word_granularity_splits_lines_into_words(client, page_image, monkeypatch):
    use_settings(monkeypatch, ocr_granularity="word")
    body = client.post("/api/lens", files=upload(page_image)).json()

    assert {region["level"] for region in body["regions"]} == {"word"}
    assert len(body["regions"]) > 6  # more regions than there are lines
    assert " " not in "".join(region["text"] for region in body["regions"])


def test_word_quads_tile_their_line_left_to_right(client, page_image, monkeypatch):
    """Word quads are carved out of the line quad, so they must not overlap and
    must stay inside it — the same invariant real engines have to satisfy."""
    use_settings(monkeypatch, ocr_granularity="word")
    body = client.post("/api/lens", files=upload(page_image)).json()

    first_line = [r for r in body["regions"] if r["id"].startswith("mock-line-0-")]
    assert len(first_line) >= 2

    for earlier, later in zip(first_line, first_line[1:], strict=False):
        assert earlier["quad"]["bbox"]["x"] < later["quad"]["bbox"]["x"]
        earlier_right = earlier["quad"]["bbox"]["x"] + earlier["quad"]["bbox"]["width"]
        assert earlier_right <= later["quad"]["bbox"]["x"] + 1


# --------------------------------------------------------------------------
# Fixture replay engine
# --------------------------------------------------------------------------


def _write_fixture(tmp_path, width: int, height: int):
    payload = {
        "image_width": width,
        "image_height": height,
        "regions": [
            {
                "id": "cv-line-0",
                "text": "recorded from a real call",
                "quad": {
                    "points": [
                        {"x": 100, "y": 200},
                        {"x": 500, "y": 200},
                        {"x": 500, "y": 260},
                        {"x": 100, "y": 260},
                    ]
                },
                "confidence": 0.93,
                "level": "line",
            }
        ],
        "full_text": "recorded from a real call",
        "engine": {"name": "cloud_vision", "duration_ms": 412, "is_mock": False},
    }
    path = tmp_path / "lens_fixture.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_fixture_engine_replays_a_saved_result(client, page_image, tmp_path, monkeypatch):
    path = _write_fixture(tmp_path, PAGE_WIDTH, PAGE_HEIGHT)
    use_settings(monkeypatch, ocr_engine="fixture", ocr_fixture_path=str(path))

    body = client.post("/api/lens", files=upload(page_image)).json()

    assert body["regions"][0]["text"] == "recorded from a real call"
    assert body["regions"][0]["quad"]["bbox"]["x"] == 100
    # It must never look like the live engine ran.
    assert body["engine"]["is_mock"] is True
    assert body["engine"]["name"] == "fixture<cloud_vision>"


def test_fixture_engine_scales_to_a_different_image_size(client, page_image, tmp_path, monkeypatch):
    path = _write_fixture(tmp_path, PAGE_WIDTH // 2, PAGE_HEIGHT // 2)
    use_settings(monkeypatch, ocr_engine="fixture", ocr_fixture_path=str(path))

    body = client.post("/api/lens", files=upload(page_image)).json()

    assert body["image_width"] == PAGE_WIDTH
    assert body["regions"][0]["quad"]["bbox"]["x"] == pytest.approx(200)


def test_missing_fixture_says_how_to_make_one(client, page_image, tmp_path, monkeypatch):
    use_settings(monkeypatch, ocr_engine="fixture", ocr_fixture_path=str(tmp_path / "absent.json"))

    response = client.post("/api/lens", files=upload(page_image))

    assert response.status_code == 503
    assert "try_engine.py" in response.json()["detail"]


def test_corrupt_fixture_is_reported_clearly(client, page_image, tmp_path, monkeypatch):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    use_settings(monkeypatch, ocr_engine="fixture", ocr_fixture_path=str(path))

    response = client.post("/api/lens", files=upload(page_image))

    assert response.status_code == 503
    assert "not a valid LensResult" in response.json()["detail"]


# --------------------------------------------------------------------------
# Credentials plumbing
# --------------------------------------------------------------------------


def test_key_path_from_dotenv_reaches_the_google_library(monkeypatch, tmp_path):
    """backend/.env is ours, not Google's. If the path never lands in os.environ
    the library ignores it, and a correct-looking config does nothing."""
    key = tmp_path / "service-account.json"
    key.write_text("{}", encoding="utf-8")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    use_settings(monkeypatch, google_application_credentials=str(key))

    apply_credentials()

    assert os.environ["GOOGLE_APPLICATION_CREDENTIALS"] == str(key)


def test_an_existing_credentials_variable_is_never_overwritten(monkeypatch, tmp_path):
    """A real shell export beats anything in .env.

    Note the setting and the environment variable share a name, so this can't go
    through `use_settings` — that would set the very variable under test. The
    .env-derived value is injected directly instead.
    """
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/already/set.json")
    monkeypatch.setattr(
        "app.services.ocr.cloud_vision.get_settings",
        lambda: Settings(google_application_credentials=str(tmp_path / "other.json")),
    )

    apply_credentials()

    assert os.environ["GOOGLE_APPLICATION_CREDENTIALS"] == "/already/set.json"


def test_unset_key_path_leaves_the_environment_alone(monkeypatch):
    """Leaving it empty is how you opt into `gcloud auth application-default
    login` — ADC is only consulted when the variable is unset."""
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    use_settings(monkeypatch)

    apply_credentials()

    assert "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ


def test_a_saved_lens_result_round_trips(client, page_image):
    """What try_engine.py saves must be exactly what the fixture engine loads."""
    body = client.post("/api/lens", files=upload(page_image)).json()
    assert LensResult.model_validate(json.loads(json.dumps(body)))
