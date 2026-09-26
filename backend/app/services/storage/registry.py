"""Picks the storage backend named by ``STORAGE_BACKEND``."""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from app.config import get_settings
from app.services.storage.base import StorageBackend, StorageError
from app.services.storage.local import LocalStorage
from app.services.storage.s3 import S3Storage

BACKENDS: dict[str, Callable[[], StorageBackend]] = {
    "local": LocalStorage,
    "s3": S3Storage,
}


@lru_cache
def get_storage() -> StorageBackend:
    name = get_settings().storage_backend
    factory = BACKENDS.get(name)
    if factory is None:
        raise StorageError(f"Unknown STORAGE_BACKEND {name!r}. Options: {', '.join(BACKENDS)}")
    return factory()
