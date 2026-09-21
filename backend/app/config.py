"""Runtime configuration, read from environment (see .env.example)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

OcrEngineName = Literal["mock", "fixture", "cloud_vision", "paddle"]
LayoutEngineName = Literal["mock", "opencv", "ppstructure", "azure"]
OcrGranularity = Literal["line", "word"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Scribble2Notes"
    environment: str = "development"

    # Comma-separated. Kept as a string so a plain .env file stays readable.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Which implementation each mode uses. Everything is behind one interface,
    # so these are the only lines that change when you swap providers.
    ocr_engine: OcrEngineName = "mock"

    # opencv by default: it needs no credentials, no weights and no GPU, so a
    # fresh clone gets real structure rather than a placeholder.
    layout_engine: LayoutEngineName = "opencv"

    # The opencv engine finds structure but cannot read; it asks the configured
    # OCR engine for the words and files them into the blocks and cells it
    # found. Turn off to get geometry only (faster, and no API calls).
    layout_fill_text: bool = True

    # Selecting a whole line feels far better than selecting word by word, so
    # engines group their output into lines by default. Switch to "word" to see
    # the raw detection granularity — useful when an engine's line grouping
    # looks wrong and you need to know whether detection or grouping is at fault.
    ocr_granularity: OcrGranularity = "line"

    # Replay a saved response instead of calling an API (OCR_ENGINE=fixture).
    # Capture one with: python scripts/try_engine.py --image page.png --save-fixture
    ocr_fixture_path: str = "fixtures/lens_fixture.json"

    # Google Cloud Vision (Mode 1 default once you have credentials)
    google_application_credentials: str | None = None

    # Azure AI Document Intelligence (managed fallback for Mode 2)
    azure_di_endpoint: str | None = None
    azure_di_key: str | None = None

    # PaddleOCR / PP-StructureV3 (self-hosted Mode 2 default)
    paddle_lang: str = "en"
    paddle_use_gpu: bool = False

    max_upload_mb: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
