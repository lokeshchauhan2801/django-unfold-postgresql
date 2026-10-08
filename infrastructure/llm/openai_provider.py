"""OpenAI LLM provider."""
from __future__ import annotations

from .interfaces import LLMProvider
from .factory import register_provider


@register_provider('openai')
class OpenAIProvider(LLMProvider):
    """Wraps OpenAI via LangChain."""

    def get_chat_model(self, model: str | None = None, temperature: float = 0.7, **kwargs):
        from django.conf import settings
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model or getattr(settings, 'DEFAULT_LLM_MODEL', 'gpt-4o-mini'),
            temperature=temperature,
            api_key=settings.OPENAI_API_KEY,
            **kwargs,
        )

    def get_embedding_model(self, model: str = 'text-embedding-3-small', **kwargs):
        from django.conf import settings
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(model=model, api_key=settings.OPENAI_API_KEY, **kwargs)

    def get_provider_name(self) -> str:
        return 'OpenAI'
