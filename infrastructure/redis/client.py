"""Redis client factory."""
from __future__ import annotations
import redis

_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis:
    global _client
    if _client is None:
        from django.conf import settings
        _client = redis.from_url(getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0'))
    return _client
