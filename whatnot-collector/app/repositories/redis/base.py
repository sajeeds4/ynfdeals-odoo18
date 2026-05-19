from __future__ import annotations

import redis

from app.config import settings


def get_client():
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)

