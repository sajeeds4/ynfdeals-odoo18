from __future__ import annotations

from app.repositories.redis.base import get_client
from app.repositories.redis.cache_repo import delete as delete_cached_json
from app.repositories.redis.cache_repo import get_json as get_cached_json
from app.repositories.redis.cache_repo import set_json as set_cached_json
from app.repositories.redis.lock_repo import acquire as acquire_lock
from app.repositories.redis.lock_repo import held_lock
from app.repositories.redis.lock_repo import release as release_lock
from app.repositories.redis.runtime_state_repo import get_state as get_runtime_state
from app.repositories.redis.runtime_state_repo import set_state as set_runtime_state


def ping() -> bool:
    try:
        return bool(get_client().ping())
    except Exception:
        return False

__all__ = [
    "acquire_lock",
    "delete_cached_json",
    "get_cached_json",
    "get_client",
    "get_runtime_state",
    "held_lock",
    "ping",
    "release_lock",
    "set_cached_json",
    "set_runtime_state",
]
