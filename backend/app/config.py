"""Runtime configuration, read from environment (see .env.example)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

OcrEngineName = Literal["mock", "cloud_vision", "paddle"]
LayoutEngineName = Literal["mock", "ppstructure", "azure"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Inkwell"
    environment: str = "development"

    # Comma-separated. Kept as a string so a plain .env file stays readable.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Which implementation each mode uses. Everything is behind one interface,
    # so these are the only lines that change when you swap providers.
    ocr_engine: OcrEngineName = "mock"
    layout_engine: LayoutEngineName = "mock"

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
