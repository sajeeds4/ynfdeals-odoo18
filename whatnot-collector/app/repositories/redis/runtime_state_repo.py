from __future__ import annotations

import json

from app.config import settings
from app.repositories.redis.base import get_client


def _key(name: str) -> str:
    return f"{settings.redis_key_prefix}:state:{name}"


def set_state(name: str, value, ttl_seconds: int | None = None) -> bool:
    payload = json.dumps(value)
    client = get_client()
    if ttl_seconds:
        return bool(client.set(_key(name), payload, ex=ttl_seconds))
    return bool(client.set(_key(name), payload))


def get_state(name: str, default=None):
    raw = get_client().get(_key(name))
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default

