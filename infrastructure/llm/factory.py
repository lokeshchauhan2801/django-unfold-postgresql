"""Registry and factory for LLM providers."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .interfaces import LLMProvider

_REGISTRY: dict[str, type] = {}


def register_provider(name: str):
    """Class decorator to register an LLM provider implementation."""
    def decorator(cls):
        _REGISTRY[name.lower()] = cls
        return cls
    return decorator


def get_provider(name: str | None = None) -> 'LLMProvider':
    """Return an LLM provider instance by name.
    Falls back to the configured default if name is None.
    """
    from django.conf import settings
    provider_name = (name or getattr(settings, 'AI_PROVIDER', 'mock')).lower()
    provider_cls = _REGISTRY.get(provider_name)
    if provider_cls is None:
        raise ValueError(f'Unknown LLM provider: {provider_name!r}. Registered: {list(_REGISTRY)}')
    return provider_cls()
