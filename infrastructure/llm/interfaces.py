"""LLM provider abstractions. Domain code depends only on these interfaces."""
from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    @abstractmethod
    def get_chat_model(self, **kwargs) -> Any:
        """Return a LangChain-compatible chat model instance."""

    @abstractmethod
    def get_embedding_model(self, **kwargs) -> Any:
        """Return a LangChain-compatible embedding model instance."""

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return a human-readable provider name."""
