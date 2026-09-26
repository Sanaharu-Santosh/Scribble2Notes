"""Where the scans live.

A third seam, following the same rule as the OCR and layout engines: callers see
one interface, an environment variable picks the implementation. Local disk is
enough to develop against and enough for a single-box deploy; object storage
matters once the host's disk becomes ephemeral, which on the free tiers this is
aimed at happens on every restart.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class StorageError(RuntimeError):
    """The backend is selected but cannot serve the request."""


class ObjectNotFound(StorageError):
    """Asked for a key that isn't there."""


class StorageBackend(ABC):
    name: str = "unnamed"

    @abstractmethod
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    async def get(self, key: str) -> bytes: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...
