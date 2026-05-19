from __future__ import annotations

import json

from app.config import settings
from app.repositories.redis.base import get_client


def _key(name: str) -> str:
    return f"{settings.redis_key_prefix}:cache:{name}"


def set_json(name: str, value, ttl_seconds: int | None = None) -> bool:
    payload = json.dumps(value)
    client = get_client()
    if ttl_seconds:
        return bool(client.set(_key(name), payload, ex=ttl_seconds))
    return bool(client.set(_key(name), payload))


def get_json(name: str, default=None):
    raw = get_client().get(_key(name))
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def delete(name: str) -> int:
    return int(get_client().delete(_key(name)))

