import unittest

from server.redis_sync import RedisSyncService


class FakeSidecar:
    def __init__(self):
        self.json_writes = {}
        self.published = []
        self.streams = []

    def set_json(self, key, payload, ttl_sec=None):
        self.json_writes[key] = {"payload": payload, "ttl_sec": ttl_sec}
        return True

    def publish_json(self, channel, payload):
        self.published.append((channel, payload))
        return True

    def append_stream_json(self, stream_name, payload, maxlen=None):
        self.streams.append((stream_name, payload, maxlen))
        return "1-0"


class RedisSyncTests(unittest.TestCase):
    def setUp(self):
        self.sidecar = FakeSidecar()
        self.service = RedisSyncService(
            sidecar=self.sidecar,
            load_collector_state_fn=lambda: {"running": True, "session_id": 61},
            load_shared_scan_state_fn=lambda: {"61": {"barcode": "123"}},
            list_company_sessions_fn=lambda account, limit=100: [
                {"id": 61, "status": "live", "name": "S61", "stream_url": "whatnot:ynfdeals"}
            ],
            get_company_session_fn=lambda session_id: {"id": int(session_id), "status": "live", "total_revenue": 370.0},
            list_pending_winner_assignments_fn=lambda session_id, statuses=None, limit=250: [
                {"id": 1, "lot_number": "40", "status": "pending"}
            ],
            list_auction_results_fn=lambda session_id=None, limit=250: [
                {"id": 99, "lot_number": "39", "sale_price": 16.0}
            ],
        )

    def test_sync_live_bundle_writes_expected_keys(self):
        results = self.service.sync_live_bundle()
        keys = {item.key for item in results}
        self.assertIn("sync:collector_state", keys)
        self.assertIn("sync:shared_scan_state", keys)
        self.assertIn("sync:sessions:ynfdeals", keys)
        self.assertIn("sync:session:61", keys)
        self.assertIn("sync:pending_winners:61", keys)
        self.assertIn("sync:auction_results:61", keys)
        self.assertEqual(self.sidecar.json_writes["sync:collector_state"]["payload"]["session_id"], 61)

    def test_publish_and_append_event(self):
        self.assertTrue(self.service.publish_event("winner", {"lot": 40}))
        self.assertEqual(self.sidecar.published[0][0], "sync_event:winner")
        entry_id = self.service.append_event("winners", {"lot": 40}, maxlen=50)
        self.assertEqual(entry_id, "1-0")
        self.assertEqual(self.sidecar.streams[0][0], "sync_event:winners")


if __name__ == "__main__":
    unittest.main()
