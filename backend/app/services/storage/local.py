"""Scans on local disk. The default, and all a single-box deploy needs."""

from __future__ import annotations

from pathlib import Path

from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.services.storage.base import ObjectNotFound, StorageBackend, StorageError


class LocalStorage(StorageBackend):
    name = "local"

    def __init__(self) -> None:
        self._root = Path(get_settings().storage_local_dir).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Keys are built server-side, but resolving and re-checking costs
        # nothing and means a key can never walk out of the storage root.
        candidate = (self._root / key).resolve()
        if not candidate.is_relative_to(self._root):
            raise StorageError(f"Refusing a key that escapes the storage root: {key!r}")
        return candidate

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        await run_in_threadpool(path.write_bytes, data)

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise ObjectNotFound(key)
        return await run_in_threadpool(path.read_bytes)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            await run_in_threadpool(path.unlink)
