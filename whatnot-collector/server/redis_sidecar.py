"""
Optional Redis sidecar for future live-state acceleration.

This module is intentionally isolated from the main runtime. Nothing should
depend on it unless REDIS_ENABLED is explicitly turned on later.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass

from .config import (
    REDIS_ENABLED,
    REDIS_HEALTH_CACHE_SEC,
    REDIS_LEASE_TTL_SEC,
    REDIS_PREFIX,
    REDIS_SOCKET_CONNECT_TIMEOUT_SEC,
    REDIS_SOCKET_TIMEOUT_SEC,
    REDIS_URL,
)

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    redis = None


@dataclass
class RedisStatus:
    enabled: bool
    available: bool
    connected: bool
    url: str
    prefix: str
    latency_ms: float | None = None
    last_error: str | None = None


@dataclass
class RedisLease:
    lease_name: str
    owner_id: str
    token: str
    heartbeat_ts: float
    ttl_sec: int

    def to_payload(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


class RedisSidecar:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        url: str | None = None,
        prefix: str | None = None,
        socket_connect_timeout_sec: float | None = None,
        socket_timeout_sec: float | None = None,
        health_cache_sec: float | None = None,
    ):
        self.enabled = REDIS_ENABLED if enabled is None else bool(enabled)
        self.url = url or REDIS_URL
        self.prefix = (prefix or REDIS_PREFIX).strip(":")
        self.socket_connect_timeout_sec = float(
            REDIS_SOCKET_CONNECT_TIMEOUT_SEC if socket_connect_timeout_sec is None else socket_connect_timeout_sec
        )
        self.socket_timeout_sec = float(
            REDIS_SOCKET_TIMEOUT_SEC if socket_timeout_sec is None else socket_timeout_sec
        )
        self.health_cache_sec = float(REDIS_HEALTH_CACHE_SEC if health_cache_sec is None else health_cache_sec)
        self._client = None
        self._last_error = None
        self._last_ping_ok = None
        self._last_ping_at = 0.0
        self._last_ping_latency_ms = None

    def available(self) -> bool:
        return redis is not None

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    def _record_error(self, exc: Exception | str | None):
        self._last_error = str(exc) if exc else None

    def _reset_client(self):
        self._client = None

    def client(self):
        if not self.enabled or redis is None:
            return None
        if self._client is None:
            self._client = redis.Redis.from_url(
                self.url,
                decode_responses=True,
                socket_connect_timeout=self.socket_connect_timeout_sec,
                socket_timeout=self.socket_timeout_sec,
                health_check_interval=15,
                retry_on_timeout=True,
            )
        return self._client

    def _call(self, fn, default=None):
        client = self.client()
        if client is None:
            return default
        try:
            value = fn(client)
            self._record_error(None)
            return value
        except Exception as exc:
            self._record_error(exc)
            self._reset_client()
            return default

    def ping(self, *, force: bool = False) -> bool:
        if not self.enabled or redis is None:
            return False
        now = time.time()
        if (
            not force
            and self._last_ping_ok is not None
            and (now - self._last_ping_at) <= max(0.0, self.health_cache_sec)
        ):
            return bool(self._last_ping_ok)
        started = time.time()
        ok = bool(self._call(lambda client: client.ping(), default=False))
        self._last_ping_ok = ok
        self._last_ping_at = time.time()
        self._last_ping_latency_ms = round((self._last_ping_at - started) * 1000.0, 2)
        return ok

    def status(self) -> RedisStatus:
        connected = self.ping() if self.enabled else False
        return RedisStatus(
            enabled=self.enabled,
            available=self.available(),
            connected=connected,
            url=self.url,
            prefix=self.prefix,
            latency_ms=self._last_ping_latency_ms if connected else None,
            last_error=self._last_error,
        )

    def get_json(self, key: str, default=None):
        raw = self._call(lambda client: client.get(self._key(key)))
        if not raw:
            return default
        try:
            return json.loads(raw)
        except Exception:
            return default

    def set_json(self, key: str, value, ttl_sec: int | None = None) -> bool:
        payload = json.dumps(value, sort_keys=True)

        def _write(client):
            if ttl_sec:
                return client.setex(self._key(key), int(ttl_sec), payload)
            return client.set(self._key(key), payload)

        return bool(self._call(_write, default=False))

    def delete(self, key: str) -> bool:
        return bool(self._call(lambda client: client.delete(self._key(key)), default=False))

    def publish_json(self, channel: str, payload) -> bool:
        return bool(self._call(lambda client: client.publish(self._key(channel), json.dumps(payload, sort_keys=True)), default=False))

    def append_stream_json(self, stream_name: str, payload, maxlen: int | None = None) -> str | None:
        def _write(client):
            kwargs = {}
            if maxlen:
                kwargs["maxlen"] = int(maxlen)
                kwargs["approximate"] = True
            return client.xadd(self._key(f"stream:{stream_name}"), {"payload": json.dumps(payload, sort_keys=True)}, **kwargs)

        return self._call(_write)

    def incr_counter(self, counter_name: str, amount: int = 1) -> int | None:
        return self._call(lambda client: int(client.incrby(self._key(f"counter:{counter_name}"), int(amount))))

    def _lease_key(self, lease_name: str) -> str:
        return self._key(f"lease:{lease_name}")

    def read_lease(self, lease_name: str) -> RedisLease | None:
        raw = self._call(lambda client: client.get(self._lease_key(lease_name)))
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return RedisLease(
                lease_name=str(data.get("lease_name") or lease_name),
                owner_id=str(data.get("owner_id") or ""),
                token=str(data.get("token") or ""),
                heartbeat_ts=float(data.get("heartbeat_ts") or 0.0),
                ttl_sec=int(data.get("ttl_sec") or REDIS_LEASE_TTL_SEC),
            )
        except Exception:
            return None

    def acquire_lease(self, lease_name: str, owner_id: str, ttl_sec: int | None = None, token: str | None = None) -> RedisLease | None:
        ttl = int(ttl_sec or REDIS_LEASE_TTL_SEC)
        lease = RedisLease(
            lease_name=lease_name,
            owner_id=str(owner_id),
            token=str(token or uuid.uuid4().hex),
            heartbeat_ts=time.time(),
            ttl_sec=ttl,
        )

        created = self._call(
            lambda client: client.set(self._lease_key(lease_name), lease.to_payload(), ex=ttl, nx=True),
            default=False,
        )
        return lease if created else None

    def renew_lease(self, lease_name: str, owner_id: str, token: str, ttl_sec: int | None = None) -> bool:
        ttl = int(ttl_sec or REDIS_LEASE_TTL_SEC)
        current = self.read_lease(lease_name)
        if current is None:
            return False
        if str(current.owner_id) != str(owner_id) or str(current.token) != str(token):
            return False
        current.heartbeat_ts = time.time()
        current.ttl_sec = ttl
        return bool(self._call(lambda client: client.set(self._lease_key(lease_name), current.to_payload(), ex=ttl), default=False))

    def claim_or_renew_lease(self, lease_name: str, owner_id: str, token: str | None = None, ttl_sec: int | None = None) -> RedisLease | None:
        current = self.read_lease(lease_name)
        if current is None:
            return self.acquire_lease(lease_name, owner_id, ttl_sec=ttl_sec, token=token)
        expected_token = str(token or current.token)
        if str(current.owner_id) != str(owner_id) or str(current.token) != expected_token:
            return None
        ok = self.renew_lease(lease_name, owner_id, expected_token, ttl_sec=ttl_sec)
        return self.read_lease(lease_name) if ok else None

    def release_lease(self, lease_name: str, owner_id: str, token: str) -> bool:
        current = self.read_lease(lease_name)
        if current is None:
            return False
        if str(current.owner_id) != str(owner_id) or str(current.token) != str(token):
            return False
        return bool(self._call(lambda client: client.delete(self._lease_key(lease_name)), default=False))

    def heartbeat(self, name: str, payload: dict | None = None, ttl_sec: int | None = None) -> bool:
        data = {
            "name": name,
            "heartbeat_ts": time.time(),
        }
        if payload:
            data.update(payload)
        return self.set_json(f"heartbeat:{name}", data, ttl_sec=ttl_sec or max(2, REDIS_LEASE_TTL_SEC))


def get_redis_sidecar() -> RedisSidecar:
    return RedisSidecar()
