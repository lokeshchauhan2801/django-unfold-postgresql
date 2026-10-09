"""Storage backend abstractions."""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO


class StorageBackend(ABC):
    """Abstract storage backend. Replace LocalStorageBackend with S3StorageBackend without changing domain code."""

    @abstractmethod
    def save(self, path: str, content: BinaryIO) -> str:
        """Save content to path. Return the full storage URL or path."""

    @abstractmethod
    def delete(self, path: str) -> None:
        """Delete a file at path."""

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Return True if path exists."""

    @abstractmethod
    def url(self, path: str) -> str:
        """Return a publicly accessible URL for path."""

    @abstractmethod
    def read(self, path: str) -> bytes:
        """Read and return file contents."""
