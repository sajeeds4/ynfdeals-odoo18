"""
Embedded Redis bootstrap for local sidecar usage.

We use redislite so this project can spin up a Redis-compatible sidecar without
requiring system redis-server or root access.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import REDIS_EMBEDDED_DB_PATH, REDIS_EMBEDDED_STATE_PATH

try:
    from redislite import Redis as EmbeddedRedis
except Exception:  # pragma: no cover
    EmbeddedRedis = None


@dataclass
class EmbeddedRedisState:
    db_path: str
    socket_path: str
    url: str


class EmbeddedRedisManager:
    def __init__(
        self,
        *,
        db_path: str | None = None,
        state_path: str | None = None,
    ):
        self.db_path = str(db_path or REDIS_EMBEDDED_DB_PATH)
        self.state_path = str(state_path or REDIS_EMBEDDED_STATE_PATH)
        self._redis = None

    def available(self) -> bool:
        return EmbeddedRedis is not None

    def start(self) -> EmbeddedRedisState:
        if EmbeddedRedis is None:
            raise RuntimeError("redislite is not installed in the active environment")
        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        self._redis = EmbeddedRedis(str(db_file))
        socket_path = str(self._redis.socket_file)
        state = EmbeddedRedisState(
            db_path=str(db_file),
            socket_path=socket_path,
            url=f"unix://{socket_path}?db=0",
        )
        Path(self.state_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.state_path).write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")
        return state

    def client(self):
        return self._redis

    def stop(self) -> None:
        if self._redis is None:
            return
        try:
            self._redis.shutdown()
        finally:
            self._redis = None
            try:
                Path(self.state_path).unlink(missing_ok=True)
            except Exception:
                pass
