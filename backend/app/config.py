"""Runtime configuration, read from environment (see .env.example)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

OcrEngineName = Literal["mock", "fixture", "cloud_vision", "paddle", "crnn"]
CrnnDecoder = Literal["greedy", "beam"]
LayoutEngineName = Literal["mock", "opencv", "ppstructure", "azure"]
OcrGranularity = Literal["line", "word"]
StorageBackendName = Literal["local", "s3"]


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

    # The from-scratch CRNN (OCR_ENGINE=crnn). Offline, free, and limited to a
    # lowercase a-z charset — see app/services/ocr/crnn.py before relying on it.
    crnn_model_path: str = "models/crnn/crnn_inference_model.keras"
    crnn_charset_path: str = "models/crnn/charset.txt"
    # greedy by default despite beam search being implemented: measured on a
    # real page, beam scored 52.6% CER against greedy's 50.7%, and on the
    # model's own training distribution the two agree exactly. Beam search pays
    # off when the probability mass is spread sensibly; this model is confidently
    # wrong rather than uncertain, so a wider search finds a likelier wrong
    # answer. Revisit after retraining — see docs/crnn-engine.md.
    crnn_decoder: CrnnDecoder = "greedy"

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

    # ---- persistence (Phase 5) -----------------------------------------
    database_url: str = "postgresql+asyncpg://scribble:scribble@localhost:5432/scribble2notes"
    database_echo: bool = False

    # local: scans on disk, fine for development and a single-box deploy
    # s3   : any S3-compatible bucket (AWS, Cloudflare R2, MinOS) — written,
    #        never run; see app/services/storage/s3.py
    storage_backend: StorageBackendName = "local"
    storage_local_dir: str = "var/storage"

    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    s3_region: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None

    # There is no sign-in yet, so every request resolves to this one account.
    # See app/services/auth.py — that is where a real provider drops in.
    dev_user_email: str = "you@localhost"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


def normalize_database_url(url: str) -> str:
    """Make a connection string copied from a hosting provider actually work.

    Every managed Postgres — Neon, Supabase, Render, Railway — hands out a libpq
    URL, and three things about it break asyncpg:

    * the scheme is ``postgres://`` or ``postgresql://``, so SQLAlchemy picks the
      sync driver and the app fails at startup with "greenlet_spawn has not
      been called";
    * ``?sslmode=require`` becomes ``connect(sslmode=...)``, which asyncpg
      rejects with ``TypeError: unexpected keyword argument 'sslmode'``. The
      parameter it wants is spelled ``ssl`` and takes the same values;
    * ``?channel_binding=require`` (Neon includes it) is rejected the same way.

    Each is a confusing failure at the moment someone is trying to deploy, so
    the URL is normalised here rather than in a README instruction people paste
    past.
    """
    parsed = urlsplit(url)

    scheme = parsed.scheme
    if scheme in {"postgres", "postgresql"}:
        scheme = "postgresql+asyncpg"

    kept: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key == "sslmode":
            kept.append(("ssl", value))
        elif key == "channel_binding":
            continue  # libpq-only; asyncpg negotiates this itself
        else:
            kept.append((key, value))

    return urlunsplit((scheme, parsed.netloc, parsed.path, urlencode(kept), parsed.fragment))


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # Assigning back rather than validating in place keeps one normalised value
    # everywhere — the app, Alembic and the tests all read this same object.
    settings.database_url = normalize_database_url(settings.database_url)
    return settings
