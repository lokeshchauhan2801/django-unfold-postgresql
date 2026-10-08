"""Local filesystem storage backend."""
from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO

from .interfaces import StorageBackend


class LocalStorageBackend(StorageBackend):
    """Stores files on the local filesystem under MEDIA_ROOT."""

    def __init__(self, base_dir: str | None = None):
        from django.conf import settings
        self.base_dir = Path(base_dir or settings.MEDIA_ROOT)

    def _full_path(self, path: str) -> Path:
        return self.base_dir / path

    def save(self, path: str, content: BinaryIO) -> str:
        full = self._full_path(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        with open(full, 'wb') as f:
            f.write(content.read() if hasattr(content, 'read') else content)
        return path

    def delete(self, path: str) -> None:
        full = self._full_path(path)
        if full.exists():
            full.unlink()

    def exists(self, path: str) -> bool:
        return self._full_path(path).exists()

    def url(self, path: str) -> str:
        from django.conf import settings
        return f'{settings.MEDIA_URL}{path}'

    def read(self, path: str) -> bytes:
        return self._full_path(path).read_bytes()
