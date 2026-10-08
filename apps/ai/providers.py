from __future__ import annotations

from typing import Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from pydantic import BaseModel

try:
    from langchain_openai import ChatOpenAI
except ImportError:  # pragma: no cover - optional dependency for local dev
    ChatOpenAI = None


class AIProvider(Protocol):
    def generate_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
    ) -> BaseModel:
        """Return a completion validated against the requested response schema."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings aligned with the input documents."""

    def embed_query(self, text: str) -> list[float]:
        """Return an embedding for a search query."""


class OpenAICompatibleProvider:
    def __init__(self, model: str | None = None):
        self.model = model or getattr(settings, "DEFAULT_LLM_MODEL", "gpt-4o-mini")
        self.provider_name = getattr(settings, "AI_PROVIDER", "openai")
        if ChatOpenAI is None:
            raise ImproperlyConfigured(
                "Install the langchain-openai package to use the configured AI provider."
            )
        api_key = getattr(settings, "AI_API_KEY", None) or settings.OPENAI_API_KEY
        if not api_key:
            raise ImproperlyConfigured(
                "Set AI_API_KEY or OPENAI_API_KEY to enable chat."
            )

        client_options = {
            "model": self.model,
            "temperature": 0.2,
            "api_key": api_key,
        }
        base_url = getattr(settings, "AI_BASE_URL", None)
        if base_url:
            client_options["base_url"] = base_url
        self.client = ChatOpenAI(**client_options)
        self._embedding_client = None

    def generate_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
    ) -> BaseModel:
        structured_client = self.client
        if self.provider_name == "openai_compatible":
            structured_client = self.client.with_structured_output(
                schema,
                method="function_calling",
            )
        else:
            structured_client = self.client.with_structured_output(schema)
        response = structured_client.invoke(prompt)
        if isinstance(response, schema):
            return response
        return schema.model_validate(response)

    @property
    def embedding_client(self):
        if self._embedding_client is None:
            from langchain_openai import OpenAIEmbeddings

            self._embedding_client = OpenAIEmbeddings(
                model=getattr(settings, "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
                api_key=settings.OPENAI_API_KEY,
            )
        return self._embedding_client

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embedding_client.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self.embedding_client.embed_query(text)


def get_ai_provider() -> AIProvider:
    provider_name = getattr(settings, "AI_PROVIDER", "openai").lower()
    if provider_name not in {"openai", "openai_compatible"}:
        raise ImproperlyConfigured(
            f"Unsupported AI_PROVIDER '{provider_name}'. "
            "Use 'openai' or 'openai_compatible'."
        )
    return OpenAICompatibleProvider()
