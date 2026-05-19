from __future__ import annotations

from contextlib import contextmanager

from app.config import settings
from app.repositories.redis.base import get_client


def _key(name: str) -> str:
    return f"{settings.redis_key_prefix}:lock:{name}"


def acquire(name: str, owner: str, ttl_seconds: int = 30) -> bool:
    return bool(get_client().set(_key(name), owner, nx=True, ex=ttl_seconds))


def release(name: str) -> int:
    return int(get_client().delete(_key(name)))


@contextmanager
def held_lock(name: str, owner: str, ttl_seconds: int = 30):
    acquired = acquire(name, owner=owner, ttl_seconds=ttl_seconds)
    try:
        yield acquired
    finally:
        if acquired:
            release(name)

