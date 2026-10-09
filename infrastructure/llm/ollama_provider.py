"""Ollama local LLM provider."""
from __future__ import annotations

from .interfaces import LLMProvider
from .factory import register_provider


@register_provider('ollama')
class OllamaProvider(LLMProvider):
    """Wraps a locally running Ollama instance via LangChain."""

    def get_chat_model(self, model: str | None = None, **kwargs):
        from django.conf import settings
        from langchain_community.chat_models import ChatOllama
        return ChatOllama(
            model=model or getattr(settings, 'DEFAULT_LLM_MODEL', 'llama3.2'),
            base_url=getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434'),
            **kwargs,
        )

    def get_embedding_model(self, model: str = 'nomic-embed-text', **kwargs):
        from django.conf import settings
        from langchain_community.embeddings import OllamaEmbeddings
        return OllamaEmbeddings(
            model=model,
            base_url=getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434'),
            **kwargs,
        )

    def get_provider_name(self) -> str:
        return 'Ollama'
