import json
import unittest

import server.redis_sidecar as redis_sidecar
from server.redis_sidecar import RedisSidecar


class FakeRedisClient:
    def __init__(self):
        self.store = {}
        self.channels = []
        self.streams = {}
        self.counters = {}

    def ping(self):
        return True

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    def setex(self, key, ttl, value):
        self.store[key] = value
        return True

    def delete(self, key):
        existed = key in self.store
        self.store.pop(key, None)
        return 1 if existed else 0

    def publish(self, channel, payload):
        self.channels.append((channel, payload))
        return 1

    def xadd(self, stream_name, fields, **kwargs):
        rows = self.streams.setdefault(stream_name, [])
        entry_id = f"{len(rows) + 1}-0"
        rows.append((entry_id, fields, kwargs))
        return entry_id

    def incrby(self, key, amount):
        self.counters[key] = int(self.counters.get(key, 0)) + int(amount)
        return self.counters[key]


class FakeRedisModule:
    class Redis:
        _client = None

        @classmethod
        def from_url(cls, *args, **kwargs):
            return cls._client


class RedisSidecarTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeRedisClient()
        self._orig_redis = redis_sidecar.redis
        FakeRedisModule.Redis._client = self.fake
        redis_sidecar.redis = FakeRedisModule
        self.sidecar = RedisSidecar(enabled=True, prefix="test", url="redis://fake")

    def tearDown(self):
        redis_sidecar.redis = self._orig_redis

    def test_json_roundtrip_and_publish(self):
        self.assertTrue(self.sidecar.set_json("state", {"lot": 12}, ttl_sec=5))
        self.assertEqual(self.sidecar.get_json("state"), {"lot": 12})
        self.assertTrue(self.sidecar.publish_json("events", {"winner": "Akeem"}))
        self.assertEqual(len(self.fake.channels), 1)
        self.assertEqual(self.fake.channels[0][0], "test:events")

    def test_stream_append_and_counter(self):
        entry_id = self.sidecar.append_stream_json("winners", {"lot": 99}, maxlen=100)
        self.assertEqual(entry_id, "1-0")
        self.assertEqual(self.sidecar.incr_counter("lot_seq"), 1)
        self.assertEqual(self.sidecar.incr_counter("lot_seq", 4), 5)

    def test_lease_acquire_renew_release(self):
        lease = self.sidecar.acquire_lease("collector", "active-a", ttl_sec=10)
        self.assertIsNotNone(lease)
        self.assertEqual(lease.owner_id, "active-a")
        self.assertFalse(self.sidecar.acquire_lease("collector", "active-b", ttl_sec=10))
        self.assertTrue(self.sidecar.renew_lease("collector", "active-a", lease.token, ttl_sec=10))
        self.assertFalse(self.sidecar.renew_lease("collector", "active-a", "wrong-token", ttl_sec=10))
        self.assertFalse(self.sidecar.release_lease("collector", "active-a", "wrong-token"))
        self.assertTrue(self.sidecar.release_lease("collector", "active-a", lease.token))
        self.assertIsNone(self.sidecar.read_lease("collector"))

    def test_claim_or_renew_respects_owner(self):
        lease = self.sidecar.claim_or_renew_lease("collector", "active-a", ttl_sec=6)
        self.assertIsNotNone(lease)
        self.assertIsNone(self.sidecar.claim_or_renew_lease("collector", "standby-b", ttl_sec=6))
        renewed = self.sidecar.claim_or_renew_lease("collector", "active-a", token=lease.token, ttl_sec=6)
        self.assertIsNotNone(renewed)
        stored = json.loads(self.fake.store["test:lease:collector"])
        self.assertEqual(stored["owner_id"], "active-a")


if __name__ == "__main__":
    unittest.main()
