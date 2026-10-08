"""Vector store abstractions."""
from abc import ABC, abstractmethod
from typing import Any


class VectorStore(ABC):
    @abstractmethod
    def add_documents(self, documents: list[dict], collection: str) -> list[str]:
        """Add documents to a collection. Return list of IDs."""

    @abstractmethod
    def similarity_search(self, query: str, collection: str, k: int = 5, filter: dict | None = None) -> list[dict]:
        """Return top-k relevant documents for query."""

    @abstractmethod
    def delete_collection(self, collection: str) -> None:
        """Delete an entire collection."""

    @abstractmethod
    def delete_documents(self, ids: list[str], collection: str) -> None:
        """Delete specific documents by ID."""
