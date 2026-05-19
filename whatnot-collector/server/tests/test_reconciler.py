import json
import unittest
from unittest import mock

import server.reconciler as reconciler


class FakePgCursor:
    def __init__(self, scripted_results, executed):
        self._scripted_results = list(scripted_results)
        self._executed = executed
        self.description = []
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        normalized = " ".join(str(query).split())
        self._executed.append((normalized, params))
        lowered = normalized.lower()
        if lowered.startswith("select"):
            if not self._scripted_results:
                raise AssertionError(f"Unexpected SELECT query: {normalized}")
            columns, rows = self._scripted_results.pop(0)
            self.description = [(column,) for column in columns]
            self._rows = list(rows)
        else:
            self.description = []
            self._rows = []

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakePgConnection:
    def __init__(self, scripted_results):
        self.executed = []
        self._scripted_results = list(scripted_results)
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return FakePgCursor(self._scripted_results, self.executed)

    def commit(self):
        self.committed = True


class ReconcilerPostgresTests(unittest.TestCase):
    def test_ensure_fact_tables_fails_closed_without_postgres(self):
        with mock.patch.object(reconciler, "postgres_available", return_value=False), \
             mock.patch.object(reconciler, "ensure_reconciler_postgres_schema") as ensure_schema:
            with self.assertRaisesRegex(RuntimeError, "reconciler_postgres_unavailable"):
                reconciler.ensure_fact_tables()

        ensure_schema.assert_not_called()

    def test_ensure_fact_tables_rejects_sqlite_db_path(self):
        with mock.patch.object(reconciler, "ensure_reconciler_postgres_schema") as ensure_schema:
            with self.assertRaisesRegex(RuntimeError, "reconciler_sqlite_runtime_retired"):
                reconciler.ensure_fact_tables("/tmp/legacy.sqlite")

        ensure_schema.assert_not_called()

    def test_list_fact_buyers_postgres_parses_streamers_json(self):
        conn = FakePgConnection(
            [
                (
                    [
                        "username",
                        "streams_seen",
                        "lots_won",
                        "total_spend",
                        "avg_sale_price",
                        "chat_messages",
                        "bids",
                        "first_seen",
                        "last_seen",
                        "buyer_tier",
                        "cross_stream_score",
                        "streamers_json",
                    ],
                    [
                        (
                            " BuyerOne ",
                            3,
                            5,
                            120.5,
                            24.1,
                            7,
                            9,
                            "2026-04-01T00:00:00Z",
                            "2026-04-02T00:00:00Z",
                            "core",
                            61.2,
                            json.dumps([{"streamer_name": "alpha"}, {"streamer_name": "beta"}]),
                        )
                    ],
                )
            ]
        )

        with mock.patch.object(reconciler, "ensure_fact_tables"), \
             mock.patch.object(reconciler, "_use_postgres_backend", return_value=True), \
             mock.patch.object(reconciler, "_pg_connect", return_value=conn):
            rows = reconciler.list_fact_buyers(limit=25)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["username"], "buyerone")
        self.assertEqual(rows[0]["streamers"], [{"streamer_name": "alpha"}, {"streamer_name": "beta"}])
        self.assertEqual(rows[0]["total_wins"], 5)
        self.assertEqual(rows[0]["messages"], 7)
        expected_fact_buyers = f"from {reconciler.POSTGRES_SIDECAR_SCHEMA}.fact_buyers"
        self.assertTrue(any(expected_fact_buyers in query.lower() for query, _ in conn.executed))

    def test_materialize_stream_intelligence_postgres_writes_signals(self):
        conn = FakePgConnection(
            [
                (
                    ["streamer_name", "status", "stale_seconds", "total_events", "non_viewer_events", "anomalies_json"],
                    [("seller-a", "healthy", 12.0, 40, 12, json.dumps({"duplicate_winner_signals": 1}))],
                ),
                (
                    [
                        "product_name",
                        "times_sold",
                        "total_revenue",
                        "avg_sale_price",
                        "median_sale_price",
                        "demand_score",
                        "resolver_confidence_avg",
                        "last_buyer",
                    ],
                    [("Rare Bottle", 3, 90.0, 30.0, 30.0, 78.0, 0.92, "buyer-a")],
                ),
                (
                    ["username", "chat_messages", "bids", "lots_won", "total_spend", "avg_sale_price", "buyer_tier"],
                    [("buyer-a", 6, 4, 2, 60.0, 30.0, "core")],
                ),
            ]
        )

        with mock.patch.object(reconciler, "ensure_fact_tables"), \
             mock.patch.object(reconciler, "materialize_stream_facts"), \
             mock.patch.object(reconciler, "materialize_stream_buyer_facts"), \
             mock.patch.object(reconciler, "materialize_stream_product_facts"), \
             mock.patch.object(reconciler, "get_competitor_listings", return_value={"listings": [{"product_name": "Rare Bottle", "starting_price": 20.0, "listing_type": "auction"}]}), \
             mock.patch.object(reconciler, "_use_postgres_backend", return_value=True), \
             mock.patch.object(reconciler, "_pg_connect", return_value=conn):
            signals = reconciler.materialize_stream_intelligence(42)

        signal_types = {item["signal_type"] for item in signals}
        self.assertIn("stream_quality", signal_types)
        self.assertIn("product_hotness", signal_types)
        self.assertIn("buyer_intent", signal_types)
        self.assertIn("price_opportunity", signal_types)
        self.assertTrue(conn.committed)

        delete_target = f"delete from {reconciler.POSTGRES_SIDECAR_SCHEMA}.intelligence_signals"
        insert_target = f"insert into {reconciler.POSTGRES_SIDECAR_SCHEMA}.intelligence_signals"
        delete_queries = [query for query, _ in conn.executed if delete_target in query.lower()]
        insert_queries = [query for query, _ in conn.executed if insert_target in query.lower()]
        self.assertEqual(len(delete_queries), 1)
        self.assertGreaterEqual(len(insert_queries), len(signals))


if __name__ == "__main__":
    unittest.main()
