from __future__ import annotations

from contextlib import ExitStack
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from fastapi.testclient import TestClient

from app.main import create_app
from app.core.ssrf import SSRFValidationError, validate_public_http_url
from app.services.legacy_mutation_service import mutate_stream_start
from app.repositories.redis import cache_repo, lock_repo, runtime_state_repo
from app.tasks.default_tasks import capture_current_session_stats, capture_runtime_diagnostics
from app.workers.celery_app import celery_app


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    def delete(self, key):
        return 1 if self.store.pop(key, None) is not None else 0

    def ping(self):
        return True


class _ProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/test"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "path": self.path}).encode("utf-8"))
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
        payload = json.loads(body.decode("utf-8") or "{}")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "payload": payload}).encode("utf-8"))

    def log_message(self, format, *args):  # noqa: A003
        return


class RuntimeStackTests(unittest.TestCase):
    def test_auth_sessions_use_signed_jwt_cookie_values(self):
        from server import auth

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(auth, "_SESSION_STORE_PATH", f"{tmp}/sessions.json"), \
                 mock.patch.object(auth, "_JWT_SECRET_PATH", f"{tmp}/jwt_secret"):
                auth._SESSIONS.clear()
                session = auth.create_session(
                    {"email": "admin@test.local", "role": "admin", "display_name": "Admin"},
                    client_ip="127.0.0.1",
                    user_agent="pytest",
                )
                token = session.get("jwt")
                self.assertEqual(2, token.count("."))
                self.assertEqual("admin@test.local", auth.get_session(token, client_ip="127.0.0.1", user_agent="pytest")["email"])
                self.assertIsNone(auth.get_session(f"{token}tampered", client_ip="127.0.0.1", user_agent="pytest"))
                self.assertEqual("admin@test.local", auth.get_session(session["id"], client_ip="127.0.0.1", user_agent="pytest")["email"])
                auth._SESSIONS.clear()

    def test_auth_session_survives_proxy_ip_and_user_agent_drift(self):
        from server import auth

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(auth, "_SESSION_STORE_PATH", f"{tmp}/sessions.json"), \
                 mock.patch.object(auth, "_JWT_SECRET_PATH", f"{tmp}/jwt_secret"):
                auth._SESSIONS.clear()
                session = auth.create_session(
                    {"email": "admin@test.local", "role": "admin", "display_name": "Admin"},
                    client_ip="192.168.1.177",
                    user_agent="Browser A",
                )
                drifted = auth.get_session(session["jwt"], client_ip="127.0.0.1", user_agent="Browser B")
                self.assertIsNotNone(drifted)
                self.assertEqual("admin@test.local", drifted["email"])
                self.assertEqual("admin@test.local", auth.get_session(session["jwt"], client_ip="192.168.1.177", user_agent="Browser A")["email"])
                auth._SESSIONS.clear()

    def test_auth_mutations_require_matching_csrf_token(self):
        from server import auth

        app = create_app(with_runtime=False)
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(auth, "_SESSION_STORE_PATH", f"{tmp}/sessions.json"), \
                 mock.patch.object(auth, "_JWT_SECRET_PATH", f"{tmp}/jwt_secret"), \
                 mock.patch("app.services.legacy_auth_admin_service.auth_enabled", return_value=True):
                auth._SESSIONS.clear()
                session = auth.create_session(
                    {"email": "admin@test.local", "role": "admin", "display_name": "Admin"},
                    client_ip="testclient",
                    user_agent="testclient",
                )
                with TestClient(app) as client:
                    client.cookies.set(auth.session_cookie_name(), session["jwt"])
                    client.cookies.set(auth.csrf_cookie_name(), session["csrf_token"])
                    missing = client.post("/api/auth/sessions/revoke_all", json={})
                    self.assertEqual(403, missing.status_code)
                    self.assertEqual("csrf_failed", missing.json()["error"])
                    ok = client.post(
                        "/api/auth/sessions/revoke_all",
                        json={},
                        headers={auth.csrf_header_name(): session["csrf_token"]},
                    )
                    self.assertEqual(200, ok.status_code)
                    self.assertTrue(ok.json()["ok"])
                auth._SESSIONS.clear()

    def test_employee_login_admin_routes_require_admin_when_auth_enabled(self):
        from server import auth

        app = create_app(with_runtime=False)
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(auth, "_SESSION_STORE_PATH", f"{tmp}/sessions.json"), \
                 mock.patch.object(auth, "_JWT_SECRET_PATH", f"{tmp}/jwt_secret"), \
                 mock.patch("app.services.legacy_auth_admin_service.auth_enabled", return_value=True):
                auth._SESSIONS.clear()
                staff = auth.create_session(
                    {"email": "staff@test.local", "role": "staff", "display_name": "Staff"},
                    client_ip="testclient",
                    user_agent="testclient",
                )
                with TestClient(app) as client:
                    client.cookies.set(auth.session_cookie_name(), staff["jwt"])
                    client.cookies.set(auth.csrf_cookie_name(), staff["csrf_token"])
                    denied = client.post(
                        "/api/employee_logins/upsert",
                        json={"email": "new@test.local", "password": "Stronger!234"},
                        headers={auth.csrf_header_name(): staff["csrf_token"]},
                    )
                    self.assertEqual(403, denied.status_code)
                    self.assertEqual("forbidden", denied.json()["error"])
                auth._SESSIONS.clear()

    def test_global_api_auth_gate_blocks_legacy_routes_when_auth_enabled(self):
        from server import auth

        app = create_app(with_runtime=False)
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(auth, "_SESSION_STORE_PATH", f"{tmp}/sessions.json"), \
                 mock.patch.object(auth, "_JWT_SECRET_PATH", f"{tmp}/jwt_secret"), \
                 mock.patch("app.main.auth_enabled", return_value=True), \
                 mock.patch("app.api.legacy_reads.get_legacy_inventory", return_value={"ok": True, "items": []}):
                auth._SESSIONS.clear()
                session = auth.create_session(
                    {"email": "admin@test.local", "role": "admin", "display_name": "Admin"},
                    client_ip="testclient",
                    user_agent="testclient",
                )
                with TestClient(app) as client:
                    blocked = client.get("/api/inventory")
                    self.assertEqual(401, blocked.status_code)
                    self.assertEqual("auth_required", blocked.json()["error"])
                    lookup = client.get("/api/auth/lookup?email=admin@test.local")
                    self.assertEqual(401, lookup.status_code)
                    client.cookies.set(auth.session_cookie_name(), session["jwt"])
                    ok = client.get("/api/inventory")
                    self.assertEqual(200, ok.status_code)
                    self.assertEqual({"ok": True, "items": []}, ok.json())
                auth._SESSIONS.clear()

    def test_global_api_auth_gate_requires_csrf_for_mutations(self):
        from server import auth

        app = create_app(with_runtime=False)
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(auth, "_SESSION_STORE_PATH", f"{tmp}/sessions.json"), \
                 mock.patch.object(auth, "_JWT_SECRET_PATH", f"{tmp}/jwt_secret"), \
                 mock.patch("app.main.auth_enabled", return_value=True), \
                 mock.patch("app.api.legacy_mutations.mutate_stream_stop", return_value={"ok": True, "running": False}):
                auth._SESSIONS.clear()
                session = auth.create_session(
                    {"email": "admin@test.local", "role": "admin", "display_name": "Admin"},
                    client_ip="testclient",
                    user_agent="testclient",
                )
                with TestClient(app) as client:
                    client.cookies.set(auth.session_cookie_name(), session["jwt"])
                    missing = client.post("/api/stream_stop", json={})
                    self.assertEqual(403, missing.status_code)
                    self.assertEqual("csrf_failed", missing.json()["error"])
                    client.cookies.set(auth.csrf_cookie_name(), session["csrf_token"])
                    bad_origin = client.post(
                        "/api/stream_stop",
                        json={},
                        headers={auth.csrf_header_name(): session["csrf_token"], "Origin": "https://evil.example"},
                    )
                    self.assertEqual(403, bad_origin.status_code)
                    self.assertEqual("origin_forbidden", bad_origin.json()["error"])
                    ok = client.post(
                        "/api/stream_stop",
                        json={},
                        headers={auth.csrf_header_name(): session["csrf_token"]},
                    )
                    self.assertEqual(200, ok.status_code)
                    self.assertEqual({"ok": True, "running": False}, ok.json())
                auth._SESSIONS.clear()

    def test_route_policy_blocks_staff_from_admin_routes(self):
        from server import auth

        app = create_app(with_runtime=False)
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(auth, "_SESSION_STORE_PATH", f"{tmp}/sessions.json"), \
                 mock.patch.object(auth, "_JWT_SECRET_PATH", f"{tmp}/jwt_secret"), \
                 mock.patch("app.main.auth_enabled", return_value=True), \
                 mock.patch("app.api.legacy_sidecar_ops.mutate_legacy_create_pos_token", return_value={"ok": True, "token": {"id": 1}}):
                auth._SESSIONS.clear()
                session = auth.create_session(
                    {"email": "staff@test.local", "role": "staff", "display_name": "Staff"},
                    client_ip="testclient",
                    user_agent="testclient",
                )
                with TestClient(app) as client:
                    client.cookies.set(auth.session_cookie_name(), session["jwt"])
                    client.cookies.set(auth.csrf_cookie_name(), session["csrf_token"])
                    denied = client.post(
                        "/api/employees/pos_token/create",
                        json={"employee_name": "A"},
                        headers={auth.csrf_header_name(): session["csrf_token"]},
                    )
                    self.assertEqual(403, denied.status_code)
                    self.assertEqual("forbidden", denied.json()["error"])
                auth._SESSIONS.clear()

    def test_limited_app_route_policy_keeps_staff_access(self):
        from server.rbac import route_policy, role_allows

        self.assertTrue(role_allows("staff-read", route_policy("/api/stream_status", "GET")))
        self.assertTrue(role_allows("staff-write", route_policy("/api/obs/demo/scan", "POST")))
        self.assertFalse(role_allows("staff-read", route_policy("/api/obs/demo/scan", "POST")))

    def test_auth_user_admin_accepts_explicit_rbac_roles(self):
        from server import auth

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(auth, "_AUTH_LOG_PATH", f"{tmp}/auth_audit.log"), \
                 mock.patch.object(auth, "_SESSION_STORE_PATH", f"{tmp}/sessions.json"), \
                 mock.patch.object(auth, "_JWT_SECRET_PATH", f"{tmp}/jwt_secret"), \
                 mock.patch.object(auth, "DASHBOARD_AUTH_USERS_PATH", f"{tmp}/users.json"):
                auth._SESSIONS.clear()
                for role in ["staff-read", "staff-write"]:
                    row = auth.upsert_auth_user(
                        f"{role}@test.local",
                        role=role,
                        password="StrongPass!234",
                        actor_email="admin@test.local",
                    )
                    self.assertEqual(role, row["role"])

    def test_correct_password_bypasses_existing_login_lockout(self):
        from server import auth

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(auth, "_AUTH_LOG_PATH", f"{tmp}/auth_audit.log"), \
                 mock.patch.object(auth, "_SESSION_STORE_PATH", f"{tmp}/sessions.json"), \
                 mock.patch.object(auth, "_JWT_SECRET_PATH", f"{tmp}/jwt_secret"), \
                 mock.patch.object(auth, "DASHBOARD_AUTH_USERS_PATH", f"{tmp}/users.json"):
                auth._SESSIONS.clear()
                auth._FAILURES.clear()
                auth._LOCKOUTS.clear()
                auth._LOCKOUT_COUNTS.clear()

                auth.upsert_auth_user(
                    "admin@test.local",
                    role="admin",
                    password="StrongPass!234",
                    actor_email="admin@test.local",
                )

                for _ in range(auth._FAILURE_LIMIT):
                    ok, _, _, meta = auth.authenticate_user(
                        "admin@test.local",
                        "wrong-pass",
                        "",
                        "127.0.0.1",
                        "pytest",
                    )
                    self.assertFalse(ok)

                wait_sec = auth.check_rate_limit("admin@test.local", "127.0.0.1")
                self.assertTrue(wait_sec and wait_sec > 0)

                ok, message, session, user = auth.authenticate_user(
                    "admin@test.local",
                    "StrongPass!234",
                    "",
                    "127.0.0.1",
                    "pytest",
                )

                self.assertTrue(ok, message)
                self.assertIsNotNone(session)
                self.assertEqual("admin@test.local", user["email"])
                self.assertIsNone(auth.check_rate_limit("admin@test.local", "127.0.0.1"))

    def test_bearer_bypass_is_disabled_unless_explicitly_enabled(self):
        app = create_app(with_runtime=False)
        with mock.patch("app.main.auth_enabled", return_value=True), \
             mock.patch("app.main.API_SECRET_KEY", "secret"), \
             mock.patch("app.main.DASHBOARD_API_BEARER_BYPASS_ENABLED", False):
            with TestClient(app) as client:
                resp = client.get("/api/inventory", headers={"Authorization": "Bearer secret"})
                self.assertEqual(401, resp.status_code)
                self.assertEqual("auth_required", resp.json()["error"])

    def test_legacy_feed_health_routes_remain_public_when_auth_enabled(self):
        app = create_app(with_runtime=False)
        with mock.patch("app.main.auth_enabled", return_value=True):
            with TestClient(app) as client:
                resp = client.get("/latest_id")
                self.assertNotEqual(401, resp.status_code)

    def test_public_login_endpoint_does_not_lock_out_correct_password_by_ip_bucket(self):
        import app.main as app_main

        app_main.RATE_BUCKETS.clear()
        app = create_app(with_runtime=False)
        with mock.patch("app.main.DASHBOARD_RATE_LIMIT_LOGIN", "2/minute"):
            with TestClient(app) as client:
                self.assertEqual(400, client.post("/api/auth/login", json={}).status_code)
                self.assertEqual(400, client.post("/api/auth/login", json={}).status_code)
                still_challenged = client.post("/api/auth/login", json={})
                self.assertEqual(400, still_challenged.status_code)
                self.assertNotEqual("rate_limited", still_challenged.json().get("error"))

    def test_security_headers_include_strict_csp_and_optional_hsts(self):
        app = create_app(with_runtime=False)
        with mock.patch("app.main.DASHBOARD_HSTS_ENABLED", True):
            with TestClient(app) as client:
                resp = client.get("/api/auth/config", headers={"X-Forwarded-Proto": "https"})
                self.assertEqual(200, resp.status_code)
                self.assertIn("default-src 'self'", resp.headers.get("content-security-policy", ""))
                self.assertIn("max-age=31536000", resp.headers.get("strict-transport-security", ""))

                lan_resp = client.get("/api/auth/config", headers={"Host": "192.168.1.177:8088"})
                self.assertNotIn("cross-origin-opener-policy", lan_resp.headers)
                self.assertNotIn("strict-transport-security", lan_resp.headers)

    def test_internal_pos_routes_remain_token_scoped_under_global_auth_gate(self):
        app = create_app(with_runtime=False)
        with mock.patch("app.main.auth_enabled", return_value=True), \
             mock.patch("app.api.legacy_sidecar_ops.get_legacy_internal_pos_products", return_value={"ok": True, "rows": [{"id": 1}]}), \
             mock.patch("app.api.legacy_sidecar_ops.mutate_legacy_internal_pos_orders", return_value={"ok": True, "order": {"id": 2}}):
            with TestClient(app) as client:
                products = client.get("/api/internal_pos/products?token=pos-token")
                self.assertEqual(200, products.status_code)
                self.assertEqual({"ok": True, "rows": [{"id": 1}]}, products.json())

                order = client.post("/api/internal_pos/orders", json={"token": "pos-token", "lines": [{"product_id": 1, "qty": 1}]})
                self.assertEqual(200, order.status_code)
                self.assertEqual({"ok": True, "order": {"id": 2}}, order.json())

    def test_internal_pos_order_requires_token_at_service_boundary(self):
        from app.services.legacy_sidecar_ops_service import get_legacy_internal_pos_products, mutate_legacy_internal_pos_orders

        order_response = mutate_legacy_internal_pos_orders({"employee_name": "A", "lines": [{"product_id": 1, "qty": 1}]})
        self.assertFalse(order_response["ok"])
        self.assertEqual(400, order_response["_status"])
        self.assertEqual("token required", order_response["error"])

        products_response = get_legacy_internal_pos_products(None)
        self.assertFalse(products_response["ok"])
        self.assertEqual(400, products_response["_status"])
        self.assertEqual("token required", products_response["error"])

    def test_ssrf_guard_blocks_private_stream_urls(self):
        with self.assertRaises(SSRFValidationError):
            validate_public_http_url("http://127.0.0.1:8088/internal")
        with mock.patch("app.services.legacy_mutation_service.start_live_collector") as start:
            response = mutate_stream_start("http://169.254.169.254/latest/meta-data")
            self.assertFalse(response["ok"])
            self.assertEqual(400, response["_status"])
            self.assertEqual("stream_url_forbidden", response["error"])
            start.assert_not_called()

    def test_fastapi_health_and_v2_route(self):
        app = create_app(with_runtime=False)
        with TestClient(app) as client:
            health = client.get("/healthz")
            self.assertEqual(200, health.status_code)
            self.assertTrue(health.json()["ok"])

            api_health = client.get("/api/v2/health")
            self.assertEqual(200, api_health.status_code)
            self.assertTrue(api_health.json()["ok"])

    def test_dashboard_shell_and_feed_routes_do_not_conflict(self):
        app = create_app(with_runtime=False)
        with mock.patch("app.api.legacy_feed.get_latest_id", return_value=123), \
             mock.patch("app.api.legacy_feed._active_or_saved_stream_id", return_value=9), \
             mock.patch("app.api.legacy_feed.get_recent_events", return_value=[{"id": 122}]), \
             mock.patch("app.api.legacy_feed.get_events_since", return_value=[{"id": 123, "event_type": "chat_message"}]), \
             mock.patch("app.api.legacy_feed._process_event_side_effects"):
            with TestClient(app) as client:
                root = client.get("/")
                self.assertEqual(200, root.status_code)
                self.assertIn("YNF Deals Dashboard", root.text)
                self.assertIn("Whatnot Live Auction Dashboard", root.text)

                latest = client.get("/latest_id")
                self.assertEqual(200, latest.status_code)
                self.assertEqual({"latest_id": 123}, latest.json())

                recent = client.get("/recent?limit=1")
                self.assertEqual({"events": [{"id": 122}]}, recent.json())

                events = client.get("/events?since=122&limit=1")
                self.assertEqual({"events": [{"id": 123, "event_type": "chat_message"}], "has_more": True}, events.json())

    def test_native_legacy_routes_bypass_proxy(self):
        app = create_app(with_runtime=False)
        with mock.patch("app.api.legacy_runtime.get_legacy_stream_status", return_value={"ok": True, "running": True}), \
             mock.patch("app.api.legacy_runtime.get_legacy_session_stats", return_value={"session": {}, "current_lot": {}}):
            with TestClient(app) as client:
                stream_status = client.get("/api/stream_status")
                self.assertEqual(200, stream_status.status_code)
                self.assertEqual(True, stream_status.json()["running"])

                session_stats = client.get("/api/session_stats")
                self.assertEqual(200, session_stats.status_code)
                self.assertIn("session", session_stats.json())
                self.assertNotIn("detail", session_stats.json())

    def test_native_legacy_read_routes_bypass_proxy(self):
        app = create_app(with_runtime=False)
        with mock.patch("app.api.legacy_reads.get_legacy_inventory", return_value={"ok": True, "rows": []}), \
             mock.patch("app.api.legacy_reads.get_legacy_inventory_categories", return_value={"ok": True, "rows": []}), \
             mock.patch("app.api.legacy_reads.get_legacy_inventory_vendors", return_value={"ok": True, "rows": []}), \
             mock.patch("app.api.legacy_reads.get_legacy_session_list", return_value={"ok": True, "sessions": []}), \
             mock.patch("app.api.legacy_reads.get_legacy_session_history", return_value={"ok": True, "sessions": []}), \
             mock.patch("app.api.legacy_feed.get_events_since", return_value=[]), \
             mock.patch("app.api.legacy_feed.get_recent_events", return_value=[]):
            with TestClient(app) as client:
                self.assertEqual(200, client.get("/api/inventory").status_code)
                self.assertEqual({"ok": True, "rows": []}, client.get("/api/inventory").json())
                self.assertEqual({"ok": True, "rows": []}, client.get("/api/inventory/categories").json())
                self.assertEqual({"ok": True, "rows": []}, client.get("/api/inventory/vendors").json())
                self.assertEqual({"ok": True, "sessions": []}, client.get("/api/sessions/list").json())
                self.assertEqual({"ok": True, "sessions": []}, client.get("/api/session_history").json())
                self.assertEqual({"events": [], "has_more": False}, client.get("/events").json())
                self.assertEqual({"events": []}, client.get("/recent").json())

    def test_native_legacy_ops_routes_bypass_proxy(self):
        app = create_app(with_runtime=False)
        with mock.patch("app.api.legacy_ops.get_legacy_winner_assignment_state", return_value={"ok": True, "session": None, "rows": []}), \
             mock.patch("app.api.legacy_ops.get_legacy_orders", return_value={"ok": True, "rows": [], "total_orders": 0}), \
             mock.patch("app.api.legacy_ops.get_legacy_customers", return_value={"ok": True, "rows": []}), \
             mock.patch("app.api.legacy_ops.get_legacy_auction_results", return_value={"rows": [], "total": 0, "total_revenue": 0, "total_profit": 0}):
            with TestClient(app) as client:
                self.assertEqual({"ok": True, "session": None, "rows": []}, client.get("/api/winner_assignment/state").json())
                self.assertEqual({"ok": True, "rows": [], "total_orders": 0}, client.get("/api/orders").json())
                self.assertEqual({"ok": True, "rows": []}, client.get("/api/customers").json())
                self.assertEqual({"rows": [], "total": 0, "total_revenue": 0, "total_profit": 0}, client.get("/api/auction_results").json())

    def test_native_inventory_detail_routes_bypass_proxy(self):
        app = create_app(with_runtime=False)
        with mock.patch("app.api.legacy_inventory_detail.get_legacy_current_lot", return_value={"ok": True, "session_id": None, "lot": {}}), \
             mock.patch("app.api.legacy_inventory_detail.get_legacy_inventory_movements", return_value={"ok": True, "rows": []}), \
             mock.patch("app.api.legacy_inventory_detail.get_legacy_inventory_audit", return_value={"ok": True, "rows": []}), \
             mock.patch("app.api.legacy_inventory_detail.get_legacy_inventory_product_detail", return_value={"ok": True, "product": {"id": 1}, "movements": []}):
            with TestClient(app) as client:
                self.assertEqual({"ok": True, "session_id": None, "lot": {}}, client.get("/api/current_lot").json())
                self.assertEqual({"ok": True, "rows": []}, client.get("/api/inventory/movements").json())
                self.assertEqual({"ok": True, "rows": []}, client.get("/api/inventory/audit").json())
                self.assertEqual({"ok": True, "product": {"id": 1}, "movements": []}, client.get("/api/inventory/product_detail?product_id=1").json())

    def test_native_detail_read_routes_bypass_proxy(self):
        app = create_app(with_runtime=False)
        with mock.patch("app.api.legacy_detail_reads.get_legacy_products", return_value={"rows": []}), \
             mock.patch("app.api.legacy_detail_reads.get_legacy_products_full", return_value={"rows": []}), \
             mock.patch("app.api.legacy_detail_reads.get_legacy_customer_detail", return_value={"ok": True, "customer": {"id": 7}}), \
             mock.patch("app.api.legacy_detail_reads.get_legacy_customer_profile_lookup", return_value={"ok": True, "customer": {"id": 7}, "orders": []}), \
             mock.patch("app.api.legacy_detail_reads.get_legacy_customer_orders", return_value={"ok": True, "orders": []}), \
             mock.patch("app.api.legacy_detail_reads.get_legacy_company_history_sessions", return_value={"ok": True, "sessions": []}), \
             mock.patch("app.api.legacy_detail_reads.get_legacy_company_history_detail", return_value={"ok": True, "winners": []}), \
             mock.patch("app.api.legacy_detail_reads.get_legacy_product_profit_report", return_value={"ok": True, "rows": []}):
            with TestClient(app) as client:
                self.assertEqual({"rows": []}, client.get("/api/products").json())
                self.assertEqual({"rows": []}, client.get("/api/products_full").json())
                self.assertEqual({"ok": True, "customer": {"id": 7}}, client.get("/api/customers/detail?customer_id=7").json())
                self.assertEqual({"ok": True, "customer": {"id": 7}, "orders": []}, client.get("/api/customers/profile_lookup?customer_id=7").json())
                self.assertEqual({"ok": True, "orders": []}, client.get("/api/customers/orders?partner_id=7").json())
                reviews = client.get("/api/customers/reviews")
                self.assertEqual(410, reviews.status_code)
                self.assertEqual({"ok": False, "error": "reviews_feature_removed"}, reviews.json())
                review_status = client.get("/api/customers/reviews/status")
                self.assertEqual(410, review_status.status_code)
                self.assertEqual({"ok": False, "error": "reviews_feature_removed"}, review_status.json())
                self.assertEqual({"ok": True, "sessions": []}, client.get("/api/history/company_sessions").json())
                self.assertEqual({"ok": True, "winners": []}, client.get("/api/history/company_detail?stream_id=1").json())
                self.assertEqual({"ok": True, "rows": []}, client.get("/api/reports/product_profit").json())

    def test_native_facts_and_product_profit_routes_bypass_proxy(self):
        app = create_app(with_runtime=False)
        with mock.patch("app.api.legacy_facts.get_legacy_fact_lots", return_value={"ok": True, "rows": [], "totals": {"rows": 0}}), \
             mock.patch("app.api.legacy_facts.get_legacy_fact_buyers", return_value={"ok": True, "rows": [], "totals": {"rows": 0}}), \
             mock.patch("app.api.legacy_facts.get_legacy_fact_products", return_value={"ok": True, "rows": [], "totals": {"rows": 0}}), \
             mock.patch("app.api.legacy_product_profit.get_legacy_product_profit", return_value={"rows": []}):
            with TestClient(app) as client:
                self.assertEqual({"ok": True, "rows": [], "totals": {"rows": 0}}, client.get("/api/facts/lots").json())
                self.assertEqual({"ok": True, "rows": [], "totals": {"rows": 0}}, client.get("/api/facts/buyers").json())
                self.assertEqual({"ok": True, "rows": [], "totals": {"rows": 0}}, client.get("/api/facts/products").json())
                self.assertEqual({"rows": []}, client.get("/api/product_profit").json())

    def test_native_mutation_routes_bypass_proxy(self):
        app = create_app(with_runtime=False)
        patches = [
            mock.patch("app.api.legacy_mutations.mutate_current_lot_set", return_value={"ok": True, "lot": {"id": 1}}),
            mock.patch("app.api.legacy_mutations.mutate_current_lot_select_product", return_value={"ok": True, "active_item": {"id": 2}}),
            mock.patch("app.api.legacy_mutations.mutate_current_lot_awaiting", return_value={"ok": True, "lot": {"id": 1, "status": "awaiting_auction"}}),
            mock.patch("app.api.legacy_mutations.mutate_current_lot_drop", return_value={"ok": True, "lot": {}}),
            mock.patch("app.api.legacy_mutations.mutate_current_lot_reuse", return_value={"ok": True, "lot": {"id": 1}}),
            mock.patch("app.api.legacy_mutations.mutate_current_lot_remove_candidate", return_value={"ok": True, "active_item": None}),
            mock.patch("app.api.legacy_mutations.mutate_current_lot_clear", return_value={"ok": True}),
            mock.patch("app.api.legacy_mutations.mutate_active_item_status", return_value={"ok": True}),
            mock.patch("app.api.legacy_mutations.mutate_reassign", return_value={"ok": False, "error": "not_supported", "_status": 400}),
            mock.patch("app.api.legacy_mutations.mutate_scan", return_value={"ok": True, "active_item": {"id": 3}}),
            mock.patch("app.api.legacy_mutations.mutate_ingest_winner", return_value={"ok": True, "result": {"session_id": 9}}),
            mock.patch("app.api.legacy_mutations.mutate_stream_start", return_value={"ok": True, "running": True}),
            mock.patch("app.api.legacy_mutations.mutate_stream_stop", return_value={"ok": True, "running": False}),
            mock.patch("app.api.legacy_mutations.mutate_winner_assignment_scan", return_value={"ok": True, "assignment": {"id": 4}}),
            mock.patch("app.api.legacy_mutations.mutate_winner_assignment_confirm", return_value={"ok": True, "assignment": {"id": 4}}),
            mock.patch("app.api.legacy_mutations.mutate_winner_assignment_undo", return_value={"ok": True, "assignment": {"id": 4}}),
            mock.patch("app.api.legacy_mutations.mutate_winner_assignment_item_delete", return_value={"ok": True, "assignment": {"id": 4}}),
            mock.patch("app.api.legacy_mutations.mutate_winner_assignment_status", return_value={"ok": True, "assignment": {"id": 4}}),
            mock.patch("app.api.legacy_mutations.mutate_winner_assignment_lot", return_value={"ok": True, "assignment": {"id": 4}, "tiktok_next_lot": None}),
            mock.patch("app.api.legacy_mutations.mutate_winner_assignment_delete", return_value={"ok": True, "deleted_assignment_id": 4}),
            mock.patch("app.api.legacy_mutations.mutate_spectator_start", return_value={"ok": True, "started": []}),
            mock.patch("app.api.legacy_mutations.mutate_spectator_stop", return_value={"ok": True, "stopped": []}),
        ]
        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            with TestClient(app) as client:
                self.assertEqual({"ok": True, "lot": {"id": 1}}, client.post("/api/current_lot/set", json={"lot_number": "12"}).json())
                self.assertEqual({"ok": True, "active_item": {"id": 2}}, client.post("/api/current_lot/select_product", json={"item_id": 2}).json())
                self.assertEqual({"ok": True, "lot": {"id": 1, "status": "awaiting_auction"}}, client.post("/api/current_lot/awaiting", json={}).json())
                self.assertEqual({"ok": True, "active_item": None}, client.post("/api/current_lot/remove_candidate", json={"item_id": 2}).json())
                self.assertEqual({"ok": True, "lot": {}}, client.post("/api/current_lot/drop", json={}).json())
                self.assertEqual({"ok": True, "lot": {"id": 1}}, client.post("/api/current_lot/reuse", json={}).json())
                self.assertEqual({"ok": True}, client.post("/api/current_lot/clear", json={}).json())
                self.assertEqual({"ok": True}, client.post("/api/active_item_status", json={"active_item_id": 2, "status": "queued"}).json())
                reassign_resp = client.post("/api/reassign", json={"auction_result_id": 1, "active_item_id": 2})
                self.assertEqual(400, reassign_resp.status_code)
                self.assertEqual({"ok": False, "error": "not_supported"}, reassign_resp.json())
                self.assertEqual({"ok": True, "active_item": {"id": 3}}, client.post("/api/scan", json={"barcode": "ABC"}).json())
                self.assertEqual({"ok": True, "result": {"session_id": 9}}, client.post("/api/ingest_winner", json={"winner_username": "a", "lot_number": "1", "event_id": 1, "sale_price": 12.0}).json())
                self.assertEqual({"ok": True, "running": True}, client.post("/api/stream_start", json={"stream_url": "https://www.whatnot.com/live/demo"}).json())
                self.assertEqual({"ok": True, "running": False}, client.post("/api/stream_stop", json={}).json())
                self.assertEqual({"ok": True, "running": True}, client.post("/api/live_collector/start", json={"stream_url": "https://www.whatnot.com/live/demo"}).json())
                self.assertEqual({"ok": True, "running": False}, client.post("/api/live_collector/stop", json={}).json())
                self.assertEqual({"ok": True, "assignment": {"id": 4}}, client.post("/api/winner_assignment/scan", json={"barcode": "ABC"}).json())
                self.assertEqual({"ok": True, "assignment": {"id": 4}}, client.post("/api/winner_assignment/confirm", json={"assignment_id": 4}).json())
                self.assertEqual({"ok": True, "assignment": {"id": 4}}, client.post("/api/winner_assignment/undo", json={"assignment_id": 4}).json())
                self.assertEqual({"ok": True, "assignment": {"id": 4}}, client.post("/api/winner_assignment/item/delete", json={"assignment_id": 4, "item_id": 5}).json())
                self.assertEqual({"ok": True, "assignment": {"id": 4}}, client.post("/api/winner_assignment/status", json={"assignment_id": 4, "status": "assigned"}).json())
                self.assertEqual({"ok": True, "assignment": {"id": 4}, "tiktok_next_lot": None}, client.post("/api/winner_assignment/lot", json={"assignment_id": 4, "lot_number": "12"}).json())
                self.assertEqual({"ok": True, "deleted_assignment_id": 4}, client.post("/api/winner_assignment/delete", json={"assignment_id": 4}).json())
                self.assertEqual({"ok": True, "started": []}, client.post("/api/spectator/start", json={"stream_urls": ["https://www.whatnot.com/live/demo"]}).json())
                self.assertEqual({"ok": True, "stopped": []}, client.post("/api/spectator/stop", json={}).json())

    def test_native_admin_mutation_routes_bypass_proxy(self):
        app = create_app(with_runtime=False)
        with mock.patch("app.api.legacy_admin_mutations.mutate_session_create", return_value={"ok": True, "id": 11, "session": {"id": 11}}), \
             mock.patch("app.api.legacy_admin_mutations.mutate_session_update", return_value={"ok": True, "session": {"id": 11}}), \
             mock.patch("app.api.legacy_admin_mutations.mutate_customer_update", return_value={"ok": True, "customer": {"id": 7}}), \
             mock.patch("app.api.legacy_admin_mutations.mutate_fee_settings_save", return_value={"ok": True}), \
             mock.patch("app.api.legacy_admin_mutations.mutate_recalc_fees", return_value={"ok": True, "updated": 5, "fee_pct": 10.9, "fixed_fee": 0.5}), \
             mock.patch("app.api.legacy_admin_mutations.mutate_inventory_category_create", return_value={"ok": True, "category": {"id": 3}}), \
             mock.patch("app.api.legacy_admin_mutations.mutate_inventory_category_delete", return_value={"ok": True}):
            with TestClient(app) as client:
                self.assertEqual({"ok": True, "id": 11, "session": {"id": 11}}, client.post("/api/sessions/create", json={"name": "Test"}).json())
                self.assertEqual({"ok": True, "session": {"id": 11}}, client.post("/api/sessions/update", json={"session_id": 11}).json())
                self.assertEqual({"ok": True, "customer": {"id": 7}}, client.post("/api/customers/update", json={"customer_id": 7}).json())
                self.assertEqual({"ok": True}, client.post("/api/fee_settings/save", json={"platform_fee_pct": 10.9}).json())
                self.assertEqual({"ok": True, "updated": 5, "fee_pct": 10.9, "fixed_fee": 0.5}, client.post("/api/recalc_fees", json={}).json())
                self.assertEqual({"ok": True, "category": {"id": 3}}, client.post("/api/inventory/categories", json={"name": "New"}).json())
                self.assertEqual({"ok": True}, client.post("/api/inventory/categories/delete", json={"id": 3}).json())

    def test_native_order_mutation_routes_bypass_proxy(self):
        app = create_app(with_runtime=False)
        with mock.patch("app.api.legacy_order_mutations.mutate_sale_order_update", return_value={"ok": True, "order": {"id": 21}}), \
             mock.patch("app.api.legacy_order_mutations.mutate_auction_result_update", return_value={"ok": True, "result": {"id": 31}}), \
             mock.patch("app.api.legacy_order_mutations.mutate_sale_order_line_save", return_value={"ok": True, "line": {"id": 41}}), \
             mock.patch("app.api.legacy_order_mutations.mutate_sale_order_line_delete", return_value={"ok": True}), \
             mock.patch("app.api.legacy_order_mutations.enqueue_sales_order_refresh"), \
             mock.patch("app.api.legacy_order_mutations.enqueue_inventory_refresh"), \
             mock.patch("app.api.legacy_order_mutations.enqueue_auction_results_refresh"):
            with TestClient(app) as client:
                self.assertEqual({"ok": True, "order": {"id": 21}}, client.post("/api/sale_orders/update", json={"order_id": 21}).json())
                self.assertEqual({"ok": True, "result": {"id": 31}}, client.post("/api/auction_results/update", json={"result_id": 31}).json())
                self.assertEqual({"ok": True, "line": {"id": 41}}, client.post("/api/sale_orders/line/save", json={"order_id": 21}).json())
                self.assertEqual({"ok": True}, client.post("/api/sale_orders/line/delete", json={"line_id": 41}).json())

    def test_business_refresh_enqueued_after_admin_mutations(self):
        app = create_app(with_runtime=False)
        with mock.patch("app.api.legacy_order_mutations.mutate_sale_order_update", return_value={"ok": True, "order": {"id": 21, "session_id": 5, "customer_id": 7}}), \
             mock.patch("app.api.legacy_order_mutations.enqueue_sales_order_refresh") as order_refresh, \
             mock.patch("app.api.legacy_order_mutations.enqueue_inventory_refresh") as inventory_refresh, \
             mock.patch("app.api.legacy_inventory_admin_mutations.mutate_inventory_product_update", return_value={"ok": True, "product": {"id": 51}}), \
             mock.patch("app.api.legacy_inventory_admin_mutations.enqueue_inventory_refresh") as admin_inventory_refresh:
            with TestClient(app) as client:
                order_resp = client.post("/api/sale_orders/update", json={"order_id": 21, "state": "sale"})
                self.assertEqual({"ok": True, "order": {"id": 21, "session_id": 5, "customer_id": 7}}, order_resp.json())
                order_refresh.assert_called_once_with(session_id=5, customer_id=7)
                inventory_refresh.assert_called_once_with()

                product_resp = client.post("/api/inventory/product/update", json={"product_id": 51, "name": "Updated"})
                self.assertEqual({"ok": True, "product": {"id": 51}}, product_resp.json())
                admin_inventory_refresh.assert_called_once_with(product_id=51)

    def test_native_inventory_admin_mutation_routes_bypass_proxy(self):
        app = create_app(with_runtime=False)
        with mock.patch("app.api.legacy_inventory_admin_mutations.mutate_inventory_product_delete", return_value={"ok": True, "deleted": 1}), \
             mock.patch("app.api.legacy_inventory_admin_mutations.mutate_inventory_product_update", return_value={"ok": True, "stock_adjusted": False, "product": {"id": 51}}), \
             mock.patch("app.api.legacy_inventory_admin_mutations.enqueue_inventory_refresh"):
            with TestClient(app) as client:
                self.assertEqual({"ok": True, "deleted": 1}, client.post("/api/inventory/product/delete", json={"product_id": 51}).json())
                self.assertEqual({"ok": True, "stock_adjusted": False, "product": {"id": 51}}, client.post("/api/inventory/product/update", json={"product_id": 51, "name": "New"}).json())

    def test_native_core_analytics_routes_bypass_proxy(self):
        app = create_app(with_runtime=False)
        with mock.patch("app.api.legacy_core_analytics.get_legacy_analytics_overview", return_value={"ok": True, "summary": {}}), \
             mock.patch("app.api.legacy_core_analytics.get_legacy_chat_signals", return_value={"ok": True, "top_keywords": [], "top_chatters": [], "recent_messages": [], "total_messages": 0}), \
             mock.patch("app.api.legacy_core_analytics.get_legacy_timing", return_value={"ok": True, "by_hour": [], "by_day": [], "best_hour": None, "best_day": None}), \
             mock.patch("app.api.legacy_core_analytics.get_legacy_company_intelligence", return_value={"ok": True, "summary": {}}), \
             mock.patch("app.api.legacy_core_analytics.get_legacy_alerts", return_value={"ok": True, "alerts": [], "count": 0}), \
             mock.patch("app.api.legacy_core_analytics.get_legacy_alert_settings", return_value={"ok": True, "margin_threshold": 0, "buyer_lots_threshold": 0, "tracked_usernames": []}):
            with TestClient(app) as client:
                self.assertEqual({"ok": True, "summary": {}}, client.get("/api/analytics/overview?stream_id=1").json())
                self.assertEqual({"ok": True, "top_keywords": [], "top_chatters": [], "recent_messages": [], "total_messages": 0}, client.get("/api/analytics/chat_signals?stream_id=1").json())
                market_pulse = client.get("/api/analytics/market_pulse")
                self.assertEqual(410, market_pulse.status_code)
                self.assertEqual({"ok": False, "error": "competitor_monitoring_retired"}, market_pulse.json())
                self.assertEqual({"ok": True, "by_hour": [], "by_day": [], "best_hour": None, "best_day": None}, client.get("/api/analytics/timing?streamer_name=demo").json())
                self.assertEqual({"ok": True, "summary": {}}, client.get("/api/company/intelligence").json())
                self.assertEqual({"ok": True, "alerts": [], "count": 0}, client.get("/api/alerts").json())
                self.assertEqual({"ok": True, "margin_threshold": 0, "buyer_lots_threshold": 0, "tracked_usernames": []}, client.get("/api/alerts/settings").json())
                spectator_listings = client.get("/api/spectator/listings?stream_id=1")
                self.assertEqual(410, spectator_listings.status_code)
                self.assertEqual({"ok": False, "error": "competitor_monitoring_retired"}, spectator_listings.json())
                competitor_prices = client.get("/api/analytics/competitor_prices")
                self.assertEqual(410, competitor_prices.status_code)
                self.assertEqual({"ok": False, "error": "competitor_monitoring_retired"}, competitor_prices.json())

    def test_native_auth_admin_routes_bypass_proxy(self):
        app = create_app(with_runtime=False)
        with ExitStack() as stack:
            stack.enter_context(mock.patch("app.main.auth_enabled", return_value=False))
            stack.enter_context(mock.patch("app.api.legacy_auth_admin.get_legacy_auth_config", return_value={"ok": True, "auth_enabled": True}))
            stack.enter_context(mock.patch("app.api.legacy_auth_admin.get_legacy_auth_me", return_value={"ok": True, "authenticated": True, "user": {"email": "admin@test"}}))
            stack.enter_context(mock.patch("app.api.legacy_auth_admin.get_legacy_auth_lookup", return_value={"ok": True, "exists": True}))
            stack.enter_context(mock.patch("app.api.legacy_auth_admin.get_legacy_auth_sessions", return_value={"ok": True, "sessions": []}))
            stack.enter_context(mock.patch("app.api.legacy_auth_admin.get_legacy_auth_rbac", return_value={"ok": True, "roles": [{"role": "admin"}, {"role": "staff"}], "route_policies": []}))
            stack.enter_context(mock.patch("app.api.legacy_auth_admin.get_legacy_auth_users", return_value={"ok": True, "users": []}))
            stack.enter_context(mock.patch("app.api.legacy_auth_admin.get_legacy_employee_logins", return_value={"ok": True, "auth_enabled": True, "users": [], "sessions": [], "activity": []}))
            stack.enter_context(mock.patch("app.api.legacy_auth_admin.get_legacy_auth_mfa_status", return_value={"ok": True, "enabled": False}))
            stack.enter_context(mock.patch("app.api.legacy_auth_admin.mutate_legacy_auth_login", return_value={"ok": True, "authenticated": True, "_headers": [("Set-Cookie", "demo=1; Path=/")]}))
            stack.enter_context(mock.patch("app.api.legacy_auth_admin.mutate_legacy_auth_logout", return_value={"ok": True, "_headers": [("Set-Cookie", "demo=; Path=/")]}))
            stack.enter_context(mock.patch("app.api.legacy_auth_admin.mutate_legacy_auth_revoke_all", return_value={"ok": True, "revoked": 2}))
            stack.enter_context(mock.patch("app.api.legacy_auth_admin.mutate_legacy_auth_password_change", return_value={"ok": True, "message": "Password updated."}))
            stack.enter_context(mock.patch("app.api.legacy_auth_admin.mutate_legacy_auth_users_upsert", return_value={"ok": True, "user": {"email": "a@test"}}))
            stack.enter_context(mock.patch("app.api.legacy_auth_admin.mutate_legacy_auth_users_revoke_sessions", return_value={"ok": True, "revoked": 1, "email": "a@test"}))
            stack.enter_context(mock.patch("app.api.legacy_auth_admin.mutate_legacy_employee_logins_upsert", return_value={"ok": True, "user": {"email": "staff@test"}}))
            stack.enter_context(mock.patch("app.api.legacy_auth_admin.mutate_legacy_employee_logins_revoke_sessions", return_value={"ok": True, "revoked": 1, "email": "staff@test"}))
            stack.enter_context(mock.patch("app.api.legacy_auth_admin.mutate_legacy_auth_mfa_setup", return_value={"ok": True, "secret": "abc"}))
            stack.enter_context(mock.patch("app.api.legacy_auth_admin.mutate_legacy_auth_mfa_confirm", return_value={"ok": True, "backup_codes": []}))
            stack.enter_context(mock.patch("app.api.legacy_auth_admin.mutate_legacy_auth_mfa_disable", return_value={"ok": True}))
            stack.enter_context(mock.patch("app.api.legacy_auth_admin.mutate_legacy_upload_cookies", return_value={"ok": True, "saved_to": "/tmp/cookies.json", "cookie_count": 2}))
            stack.enter_context(mock.patch("app.api.legacy_auth_admin.mutate_legacy_company_sync_from_odoo_removed", return_value={"ok": False, "error": "removed", "_status": 410}))
            with TestClient(app) as client:
                self.assertEqual({"ok": True, "auth_enabled": True}, client.get("/api/auth/config").json())
                self.assertEqual({"ok": True, "authenticated": True, "user": {"email": "admin@test"}}, client.get("/api/auth/me").json())
                self.assertEqual({"ok": True, "exists": True}, client.get("/api/auth/lookup?email=a@test").json())
                self.assertEqual({"ok": True, "sessions": []}, client.get("/api/auth/sessions").json())
                self.assertEqual({"ok": True, "roles": [{"role": "admin"}, {"role": "staff"}], "route_policies": []}, client.get("/api/auth/rbac").json())
                self.assertEqual({"ok": True, "users": []}, client.get("/api/auth/users").json())
                self.assertEqual({"ok": True, "auth_enabled": True, "users": [], "sessions": [], "activity": []}, client.get("/api/employee_logins").json())
                self.assertEqual({"ok": True, "enabled": False}, client.get("/api/auth/mfa/status").json())
                login_resp = client.post("/api/auth/login", json={"email": "a@test", "password": "secret"})
                self.assertEqual(200, login_resp.status_code)
                self.assertEqual({"ok": True, "authenticated": True}, login_resp.json())
                self.assertIn("demo=1", login_resp.headers.get("set-cookie", ""))
                logout_resp = client.post("/api/auth/logout", json={})
                self.assertEqual({"ok": True}, logout_resp.json())
                self.assertIn("demo=", logout_resp.headers.get("set-cookie", ""))
                self.assertEqual({"ok": True, "revoked": 2}, client.post("/api/auth/sessions/revoke_all", json={}).json())
                self.assertEqual({"ok": True, "message": "Password updated."}, client.post("/api/auth/password/change", json={}).json())
                self.assertEqual({"ok": True, "user": {"email": "a@test"}}, client.post("/api/auth/users/upsert", json={"email": "a@test"}).json())
                self.assertEqual({"ok": True, "revoked": 1, "email": "a@test"}, client.post("/api/auth/users/revoke_sessions", json={"email": "a@test"}).json())
                self.assertEqual({"ok": True, "user": {"email": "staff@test"}}, client.post("/api/employee_logins/upsert", json={"email": "staff@test"}).json())
                self.assertEqual({"ok": True, "revoked": 1, "email": "staff@test"}, client.post("/api/employee_logins/revoke_sessions", json={"email": "staff@test"}).json())
                self.assertEqual({"ok": True, "secret": "abc"}, client.post("/api/auth/mfa/setup", json={}).json())
                self.assertEqual({"ok": True, "backup_codes": []}, client.post("/api/auth/mfa/confirm", json={"otp_code": "123456"}).json())
                self.assertEqual({"ok": True}, client.post("/api/auth/mfa/disable", json={"otp_code": "123456"}).json())
                review_sync = client.post("/api/customers/reviews/sync", json={})
                self.assertEqual(410, review_sync.status_code)
                self.assertEqual({"ok": False, "error": "reviews_feature_removed"}, review_sync.json())
                self.assertEqual({"ok": True, "saved_to": "/tmp/cookies.json", "cookie_count": 2}, client.post("/api/upload_cookies", content=b'[]').json())
                removed_resp = client.post("/api/company/sync_from_odoo", json={})
                self.assertEqual(410, removed_resp.status_code)
                self.assertEqual({"ok": False, "error": "removed"}, removed_resp.json())

    def test_native_sidecar_ops_routes_bypass_proxy(self):
        app = create_app(with_runtime=False)
        with ExitStack() as stack:
            stack.enter_context(mock.patch("app.main.auth_enabled", return_value=False))
            stack.enter_context(mock.patch("app.api.legacy_sidecar_ops.get_legacy_company_prep", return_value={"ok": True, "low_stock": []}))
            stack.enter_context(mock.patch("app.api.legacy_sidecar_ops.mutate_legacy_picklist_upload", return_value={"ok": True, "pick_list_id": 12, "shipments": [], "summary": {"total_shipments": 0}}))
            stack.enter_context(mock.patch("app.api.legacy_sidecar_ops.mutate_legacy_in_house_sale", return_value={"ok": True, "sale": {"id": 1}, "sale_count": 1}))
            stack.enter_context(mock.patch("app.api.legacy_sidecar_ops.mutate_legacy_create_pos_token", return_value={"ok": True, "token": {"id": 2}}))
            stack.enter_context(mock.patch("app.api.legacy_sidecar_ops.mutate_legacy_internal_pos_orders", return_value={"ok": True, "order": {"id": 3}, "summary": {"pending_count": 1}}))
            stack.enter_context(mock.patch("app.api.legacy_sidecar_ops.mutate_legacy_in_house_order_approve", return_value={"ok": True, "order": {"id": 4}, "summary": {"approved_count": 1}, "sales": {"sale_count": 2}}))
            stack.enter_context(mock.patch("app.api.legacy_sidecar_ops.mutate_legacy_in_house_order_reject", return_value={"ok": True, "order": {"id": 5}, "summary": {"rejected_count": 1}}))
            stack.enter_context(mock.patch("app.api.legacy_sidecar_ops.mutate_legacy_in_house_order_cancel", return_value={"ok": True, "order": {"id": 6}, "summary": {"order_count": 1}}))
            stack.enter_context(mock.patch("app.api.legacy_sidecar_ops.mutate_legacy_ensure_sale_order", return_value={"ok": True, "sale_order_id": 7, "sale_order_name": "SO-7"}))
            with TestClient(app) as client:
                self.assertEqual({"ok": True, "low_stock": []}, client.get("/api/company/prep").json())
                follow = client.post("/api/users/follow", json={"username": "demo"})
                self.assertEqual(410, follow.status_code)
                self.assertEqual({"ok": False, "error": "competitor_monitoring_retired"}, follow.json())
                self.assertEqual({"ok": True, "pick_list_id": 12, "shipments": [], "summary": {"total_shipments": 0}}, client.post("/api/picklist/upload?session_id=1&filename=test.pdf", content=b"%PDF-1.4").json())
                self.assertEqual({"ok": True, "sale": {"id": 1}, "sale_count": 1}, client.post("/api/in_house_sales", json={"employee_name": "A"}).json())
                self.assertEqual({"ok": True, "token": {"id": 2}}, client.post("/api/employees/pos_token/create", json={"employee_name": "A"}).json())
                self.assertEqual({"ok": True, "order": {"id": 3}, "summary": {"pending_count": 1}}, client.post("/api/internal_pos/orders", json={"token": "pos-token", "lines": [{"product_id": 1, "qty": 1}]}).json())
                self.assertEqual({"ok": True, "order": {"id": 4}, "summary": {"approved_count": 1}, "sales": {"sale_count": 2}}, client.post("/api/in_house_orders/approve", json={"id": 4}).json())
                self.assertEqual({"ok": True, "order": {"id": 5}, "summary": {"rejected_count": 1}}, client.post("/api/in_house_orders/reject", json={"id": 5}).json())
                self.assertEqual({"ok": True, "order": {"id": 6}, "summary": {"order_count": 1}}, client.post("/api/in_house_orders/cancel", json={"id": 6}).json())
                self.assertEqual({"ok": True, "sale_order_id": 7, "sale_order_name": "SO-7"}, client.post("/api/orders/ensure_sale_order", json={"group_id": 7}).json())

    def test_native_analytics_compat_routes_bypass_proxy(self):
        app = create_app(with_runtime=False)
        with TestClient(app) as client:
            businesses = client.get("/api/analytics/businesses")
            self.assertEqual(410, businesses.status_code)
            self.assertEqual({"ok": False, "error": "competitor_monitoring_retired"}, businesses.json())

            trends = client.get("/api/analytics/trends?streamer_name=demo")
            self.assertEqual(410, trends.status_code)
            self.assertEqual({"ok": False, "error": "competitor_monitoring_retired"}, trends.json())

    def test_native_analytics_intelligence_routes_bypass_proxy(self):
        app = create_app(with_runtime=False)
        app.state.legacy_bridge_url = "http://127.0.0.1:1"
        with mock.patch(
            "app.api.legacy_analytics_intelligence.get_legacy_products_intel",
            return_value={
                "ok": True,
                "rows": [
                    {
                        "product_name": "Demo Product",
                        "times_sold": 4,
                        "total_revenue": 80.0,
                    }
                ],
                "total": 1,
            },
        ), mock.patch(
            "app.api.legacy_analytics_intelligence.get_legacy_intelligence_live",
            return_value={
                "ok": True,
                "rows": [
                    {
                        "id": 1,
                        "signal_type": "pricing",
                        "signal_label": "Price softness",
                    }
                ],
                "grouped": {
                    "pricing": [
                        {
                            "id": 1,
                            "signal_type": "pricing",
                            "signal_label": "Price softness",
                        }
                    ]
                },
            },
        ):
            with TestClient(app) as client:
                self.assertEqual(
                    {
                        "ok": True,
                        "rows": [
                            {
                                "product_name": "Demo Product",
                                "times_sold": 4,
                                "total_revenue": 80.0,
                            }
                        ],
                        "total": 1,
                    },
                    client.get("/api/analytics/products_intel?streamer_name=demo").json(),
                )
                self.assertEqual(
                    {
                        "ok": True,
                        "rows": [
                            {
                                "id": 1,
                                "signal_type": "pricing",
                                "signal_label": "Price softness",
                            }
                        ],
                        "grouped": {
                            "pricing": [
                                {
                                    "id": 1,
                                    "signal_type": "pricing",
                                    "signal_label": "Price softness",
                                }
                            ]
                        },
                    },
                    client.get("/api/intelligence/live?stream_id=12").json(),
                )

    def test_native_competitor_detection_routes_bypass_proxy(self):
        app = create_app(with_runtime=False)
        with TestClient(app) as client:
            title_quality = client.get("/api/competitors/title_quality?stream_id=12")
            self.assertEqual(410, title_quality.status_code)
            self.assertEqual({"ok": False, "error": "competitor_monitoring_retired"}, title_quality.json())

            detection_feed = client.get("/api/competitors/detection_feed?stream_id=12")
            self.assertEqual(410, detection_feed.status_code)
            self.assertEqual({"ok": False, "error": "competitor_monitoring_retired"}, detection_feed.json())

    def test_native_export_routes_bypass_proxy(self):
        app = create_app(with_runtime=False)
        app.state.legacy_bridge_url = "http://127.0.0.1:1"
        with mock.patch(
            "app.api.legacy_exports.build_auction_results_csv",
            return_value="ID,Session\n1,2\n",
        ), mock.patch(
            "app.api.legacy_exports.build_orders_csv",
            return_value="ID,Buyer\n3,demo\n",
        ), mock.patch(
            "app.api.legacy_exports.build_reports_csv",
            return_value="Product,SKU\nDemo,SKU-1\n",
        ):
            with TestClient(app) as client:
                auction_resp = client.get("/api/export/auction_results.csv?session_id=2")
                self.assertEqual(200, auction_resp.status_code)
                self.assertEqual("attachment; filename=auction_results.csv", auction_resp.headers["content-disposition"])
                self.assertTrue(auction_resp.headers["content-type"].startswith("text/csv"))
                self.assertEqual("ID,Session\n1,2\n", auction_resp.text)

                orders_resp = client.get("/api/export/orders.csv?session_id=2")
                self.assertEqual(200, orders_resp.status_code)
                self.assertEqual("attachment; filename=buyer_orders.csv", orders_resp.headers["content-disposition"])
                self.assertTrue(orders_resp.headers["content-type"].startswith("text/csv"))
                self.assertEqual("ID,Buyer\n3,demo\n", orders_resp.text)

                reports_resp = client.get("/api/export/reports.csv?session_id=2")
                self.assertEqual(200, reports_resp.status_code)
                self.assertEqual("attachment; filename=product_report.csv", reports_resp.headers["content-disposition"])
                self.assertTrue(reports_resp.headers["content-type"].startswith("text/csv"))
                self.assertEqual("Product,SKU\nDemo,SKU-1\n", reports_resp.text)

                users_resp = client.get("/api/export/users.csv")
                self.assertEqual(410, users_resp.status_code)
                self.assertEqual("competitor monitoring retired", users_resp.text)

    def test_native_shop_analytics_routes_bypass_proxy(self):
        app = create_app(with_runtime=False)
        with mock.patch(
            "app.api.legacy_shop_analytics.get_legacy_shop_products",
            return_value={
                "ok": True,
                "products": [
                    {
                        "product_name": "Demo Product",
                        "price": 19.99,
                        "qty": 3,
                        "image_url": "https://example.com/product.jpg",
                        "listing_url": "https://whatnot.com/listing/demo",
                    }
                ],
                "scraped_at": "2026-04-14T10:00:00+00:00",
                "total": 1,
            },
        ), mock.patch(
            "app.api.legacy_shop_analytics.get_legacy_shop_scrape_status",
            return_value={
                "ok": True,
                "status": "complete",
                "started_at": "2026-04-14T09:59:00+00:00",
                "finished_at": "2026-04-14T10:00:00+00:00",
                "product_count": 1,
                "error": None,
            },
        ):
            with TestClient(app) as client:
                self.assertEqual(
                    {
                        "ok": True,
                        "products": [
                            {
                                "product_name": "Demo Product",
                                "price": 19.99,
                                "qty": 3,
                                "image_url": "https://example.com/product.jpg",
                                "listing_url": "https://whatnot.com/listing/demo",
                            }
                        ],
                        "scraped_at": "2026-04-14T10:00:00+00:00",
                        "total": 1,
                    },
                    client.get("/api/analytics/shop_products?streamer_name=demo").json(),
                )
                self.assertEqual(
                    {
                        "ok": True,
                        "status": "complete",
                        "started_at": "2026-04-14T09:59:00+00:00",
                        "finished_at": "2026-04-14T10:00:00+00:00",
                        "product_count": 1,
                        "error": None,
                    },
                    client.get("/api/analytics/shop_scrape_status?streamer_name=demo").json(),
                )

    def test_native_shop_scrape_route_bypasses_proxy(self):
        app = create_app(with_runtime=False)
        with mock.patch(
            "app.api.legacy_shop_scrape.trigger_legacy_shop_scrape",
            return_value={
                "ok": True,
                "started": True,
                "status": "running",
                "started_at": "2026-04-14T11:00:00+00:00",
                "finished_at": None,
                "product_count": 0,
                "error": None,
            },
        ):
            with TestClient(app) as client:
                resp = client.post("/api/analytics/scrape_shop", json={"streamer_name": "demo"})
                self.assertEqual(200, resp.status_code)
                self.assertEqual(
                    {
                        "ok": True,
                        "started": True,
                        "status": "running",
                        "started_at": "2026-04-14T11:00:00+00:00",
                        "finished_at": None,
                        "product_count": 0,
                        "error": None,
                    },
                    resp.json(),
                )

    def test_native_tiktok_routes_bypass_proxy(self):
        app = create_app(with_runtime=False)
        app.state.legacy_bridge_url = "http://127.0.0.1:1"
        with mock.patch(
            "app.api.legacy_tiktok.get_tiktok_extractor_lot_state",
            return_value={"ok": True, "stream_url": "tiktok:demo", "next_lot": 12, "updated_at": "2026-04-14T12:00:00+00:00"},
        ), mock.patch(
            "app.api.legacy_tiktok.set_tiktok_extractor_lot_state",
            return_value={"ok": True, "stream_url": "tiktok:demo", "next_lot": 13},
        ), mock.patch(
            "app.api.legacy_tiktok.update_tiktok_operator_config",
            return_value={"ok": True, "tiktok_operator": {"enabled": True, "streamer": "demo"}},
        ), mock.patch(
            "app.api.legacy_tiktok.create_tiktok_shop_order",
            return_value={"ok": True, "order": {"id": 101}, "lines": []},
        ), mock.patch(
            "app.api.legacy_tiktok.create_tiktok_live_order",
            return_value={"ok": True, "order": {"id": 102}, "lines": []},
        ), mock.patch(
            "app.api.legacy_tiktok.import_tiktok_shop_orders",
            return_value={"ok": True, "rows": [], "summary": {"total_rows": 0}, "imported": []},
        ), mock.patch(
            "app.api.legacy_tiktok.get_tiktok_live_picklist",
            return_value={"ok": True, "shipments": [], "summary": {"total_shipments": 0}},
        ):
            with TestClient(app) as client:
                self.assertEqual(
                    {"ok": True, "stream_url": "tiktok:demo", "next_lot": 12, "updated_at": "2026-04-14T12:00:00+00:00"},
                    client.get("/api/tiktok_extractor/lot_state?stream_url=tiktok:demo").json(),
                )
                self.assertEqual(
                    {"ok": True, "stream_url": "tiktok:demo", "next_lot": 13},
                    client.post("/api/tiktok_extractor/lot_state", json={"stream_url": "tiktok:demo", "next_lot": 13}).json(),
                )
                self.assertEqual(
                    {"ok": True, "tiktok_operator": {"enabled": True, "streamer": "demo"}},
                    client.post("/api/tiktok_operator/config", json={"enabled": True, "streamer": "demo"}).json(),
                )
                self.assertEqual(
                    {"ok": True, "order": {"id": 101}, "lines": []},
                    client.post("/api/tiktok_shop_orders/create", json={"product_id": 1}).json(),
                )
                self.assertEqual(
                    {"ok": True, "order": {"id": 102}, "lines": []},
                    client.post("/api/tiktok_live_orders/create", json={"product_id": 1}).json(),
                )
                self.assertEqual(
                    {"ok": True, "rows": [], "summary": {"total_rows": 0}, "imported": []},
                    client.post("/api/tiktok_shop_orders/import_csv", json={"csv_text": "a,b\n"}).json(),
                )
                self.assertEqual(
                    {"ok": True, "shipments": [], "summary": {"total_shipments": 0}},
                    client.get("/api/tiktok_live_picklist?session_id=5").json(),
                )

    def test_native_user_cluster_routes_bypass_proxy(self):
        app = create_app(with_runtime=False)
        with TestClient(app) as client:
            for path in (
                "/api/users/cross_stream?min_streams=2",
                "/api/users/audience?q=demo",
                "/api/users/profile?username=demo",
                "/api/users/target_buyers?sellers=seller_a,seller_b",
            ):
                response = client.get(path)
                self.assertEqual(410, response.status_code)
                self.assertEqual({"ok": False, "error": "competitor_monitoring_retired"}, response.json())

    def test_native_facts_routes_bypass_proxy(self):
        app = create_app(with_runtime=False)
        app.state.legacy_bridge_url = "http://127.0.0.1:1"
        with mock.patch(
            "app.api.legacy_facts.get_legacy_fact_lots",
            return_value={
                "ok": True,
                "rows": [
                    {
                        "stream_id": 12,
                        "lot_number": "5",
                        "sale_price": 19.5,
                        "confidence_label": "high",
                    }
                ],
                "totals": {
                    "rows": 1,
                    "revenue": 19.5,
                    "high_confidence": 1,
                    "medium_confidence": 0,
                    "low_confidence": 0,
                },
            },
        ), mock.patch(
            "app.api.legacy_facts.get_legacy_fact_buyers",
            return_value={
                "ok": True,
                "rows": [
                    {
                        "username": "demo",
                        "total_spend": 42.0,
                        "lots_won": 2,
                        "chat_messages": 7,
                        "streams_seen": 2,
                        "buyer_tier": "whale",
                    }
                ],
                "totals": {
                    "rows": 1,
                    "buyers": 1,
                    "whales": 1,
                    "total_spend": 42.0,
                    "total_wins": 2,
                    "total_messages": 7,
                    "cross_stream_buyers": 1,
                },
            },
        ):
            with TestClient(app) as client:
                self.assertEqual(
                    {
                        "ok": True,
                        "rows": [
                            {
                                "stream_id": 12,
                                "lot_number": "5",
                                "sale_price": 19.5,
                                "confidence_label": "high",
                            }
                        ],
                        "totals": {
                            "rows": 1,
                            "revenue": 19.5,
                            "high_confidence": 1,
                            "medium_confidence": 0,
                            "low_confidence": 0,
                        },
                    },
                    client.get("/api/facts/lots?stream_id=12&from=2026-04-14T00:00:00Z").json(),
                )
                self.assertEqual(
                    {
                        "ok": True,
                        "rows": [
                            {
                                "username": "demo",
                                "total_spend": 42.0,
                                "lots_won": 2,
                                "chat_messages": 7,
                                "streams_seen": 2,
                                "buyer_tier": "whale",
                            }
                        ],
                        "totals": {
                            "rows": 1,
                            "buyers": 1,
                            "whales": 1,
                            "total_spend": 42.0,
                            "total_wins": 2,
                            "total_messages": 7,
                            "cross_stream_buyers": 1,
                        },
                    },
                    client.get("/api/facts/buyers?streamer_name=demo").json(),
                )

    def test_legacy_proxy_forwards_requests(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _ProxyHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        app = create_app(with_runtime=False)
        app.state.legacy_bridge_url = f"http://127.0.0.1:{server.server_port}"
        try:
            with TestClient(app) as client:
                resp = client.get("/api/test?x=1")
                self.assertEqual(200, resp.status_code)
                self.assertEqual(True, resp.json()["ok"])
                self.assertIn("/api/test?x=1", resp.json()["path"])

                post_resp = client.post("/api/test-post", json={"hello": "world"})
                self.assertEqual(200, post_resp.status_code)
                self.assertEqual({"hello": "world"}, post_resp.json()["payload"])
        finally:
            server.shutdown()
            server.server_close()

    def test_celery_config_and_tasks(self):
        self.assertEqual("default", celery_app.conf.task_default_queue)
        self.assertIn("app.tasks.default.*", celery_app.conf.task_routes)
        self.assertEqual({"queue": "business"}, celery_app.conf.task_routes["app.tasks.business.*"])
        self.assertIn("app.tasks.business_tasks", celery_app.loader.default_modules)
        with mock.patch("app.tasks.default_tasks.get_deep_runtime_diagnostics", return_value={"ok": True}), \
             mock.patch("app.tasks.default_tasks.get_current_session_stats", return_value={"ok": True}), \
             mock.patch("app.tasks.default_tasks.set_runtime_state") as mocked_state:
            self.assertEqual({"ok": True}, capture_runtime_diagnostics())
            self.assertEqual({"ok": True}, capture_current_session_stats())
            self.assertEqual(2, mocked_state.call_count)

    def test_redis_helpers(self):
        fake = _FakeRedis()
        with mock.patch("app.repositories.redis.cache_repo.get_client", return_value=fake), \
             mock.patch("app.repositories.redis.lock_repo.get_client", return_value=fake), \
             mock.patch("app.repositories.redis.runtime_state_repo.get_client", return_value=fake):
            self.assertTrue(cache_repo.set_json("sample", {"ok": True}, ttl_seconds=10))
            self.assertEqual({"ok": True}, cache_repo.get_json("sample"))
            self.assertTrue(lock_repo.acquire("job", owner="worker-1", ttl_seconds=10))
            self.assertFalse(lock_repo.acquire("job", owner="worker-2", ttl_seconds=10))
            self.assertEqual(1, lock_repo.release("job"))
            self.assertTrue(runtime_state_repo.set_state("heartbeat", {"ready": True}, ttl_seconds=5))
            self.assertEqual({"ready": True}, runtime_state_repo.get_state("heartbeat"))

    def test_runtime_diagnostics_includes_summaries(self):
        app = create_app(with_runtime=False)
        request_metrics = {
            "GET /api/v2/spectator/status": {
                "path": "/api/v2/spectator/status",
                "method": "GET",
                "count": 12,
                "status_code": 200,
                "last_duration_ms": 48.5,
                "avg_duration_ms": 32.1,
                "total_duration_ms": 385.2,
                "last_seen_at": "2026-04-14T10:00:00+00:00",
            },
            "GET /api/alerts": {
                "path": "/api/alerts",
                "method": "GET",
                "count": 2,
                "status_code": 503,
                "last_duration_ms": 200.0,
                "avg_duration_ms": 180.0,
                "total_duration_ms": 360.0,
                "last_seen_at": "2026-04-14T10:01:00+00:00",
            },
        }
        bridge_metrics = {
            "GET /api/deferred": {
                "path": "/api/deferred",
                "method": "GET",
                "count": 4,
                "status_code": 200,
                "last_seen_at": "2026-04-14T10:02:00+00:00",
            }
        }
        task_metrics = {
            "capture_runtime_diagnostics:completed": {
                "task": "capture_runtime_diagnostics",
                "outcome": "completed",
                "count": 5,
                "last_seen_at": "2026-04-14T10:03:00+00:00",
            },
            "refresh_recent_stream_facts:failed": {
                "task": "refresh_recent_stream_facts",
                "outcome": "failed",
                "count": 1,
                "last_seen_at": "2026-04-14T10:04:00+00:00",
            },
        }
        with mock.patch("app.services.diagnostics_service.ping", return_value=True), \
             mock.patch("app.services.diagnostics_service._celery_queue_health", return_value={"inspect_ok": True, "queues": []}), \
             mock.patch("app.services.diagnostics_service.get_runtime_state") as mocked_state, \
             mock.patch("app.services.diagnostics_service.get_request_metrics", return_value=request_metrics), \
             mock.patch("app.services.diagnostics_service.get_bridge_metrics", return_value=bridge_metrics), \
             mock.patch(
                 "app.services.diagnostics_service.summarize_request_metrics",
                 return_value={
                     "tracked_routes": 2,
                     "total_requests": 14,
                     "error_requests": 2,
                     "error_rate_pct": 14.29,
                     "top_routes_by_count": [request_metrics["GET /api/v2/spectator/status"]],
                     "slowest_routes_by_avg_ms": [request_metrics["GET /api/alerts"]],
                 },
             ), \
             mock.patch(
                 "app.services.diagnostics_service.summarize_bridge_metrics",
                 return_value={
                     "tracked_routes": 1,
                     "total_bridge_hits": 4,
                     "top_bridge_routes": [bridge_metrics["GET /api/deferred"]],
                 },
             ):
            mocked_state.side_effect = lambda key, default=None: {
                "diagnostics:last": {"ok": True},
                "session_stats:last": {"ok": True},
                "tasks:metrics": task_metrics,
            }.get(key, default)
            with TestClient(app) as client:
                resp = client.get("/api/v2/diagnostics/runtime")
                self.assertEqual(200, resp.status_code)
                payload = resp.json()
                self.assertEqual("runtime", payload["diagnostics_mode"])
                runtime = payload["fastapi_runtime"]["runtime_state"]
                self.assertEqual(14, runtime["request_summary"]["total_requests"])
                self.assertEqual(2, runtime["request_summary"]["error_requests"])
                self.assertEqual("/api/alerts", runtime["request_summary"]["slowest_routes_by_avg_ms"][0]["path"])
                self.assertEqual(4, runtime["bridge_summary"]["total_bridge_hits"])
                self.assertEqual("/api/deferred", runtime["bridge_summary"]["top_bridge_routes"][0]["path"])
                self.assertEqual(5, runtime["task_summary"]["outcome_totals"]["completed"])
                self.assertEqual(1, runtime["task_summary"]["outcome_totals"]["failed"])

    def test_database_status_reports_sqlite_retired_without_connecting(self):
        from app.services.database_status_service import get_database_status

        with mock.patch("app.services.database_status_service.psycopg2", None), \
             mock.patch("app.services.database_status_service.domain_primary_backend", return_value="postgres"), \
             mock.patch("app.services.database_status_service.domain_dual_write_enabled", return_value=False), \
             mock.patch("app.services.database_status_service.domain_validate_enabled", return_value=False):
            payload = get_database_status()
        self.assertFalse(payload["sqlite"]["connected"])
        self.assertTrue(payload["sqlite"]["retired"])
        self.assertEqual("sqlite_runtime_retired", payload["sqlite"]["error"])
        self.assertEqual("postgres", payload["current_primary"])
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["safe_mode"])
        self.assertTrue(payload["summary"]["fail_closed"])

    def test_database_status_fails_closed_when_schema_or_domains_incomplete(self):
        from app.services.database_status_service import get_database_status

        class FakeCursor:
            description = ()

            def __init__(self):
                self._result = (1,)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, query, params=None):
                if "information_schema.schemata" in query:
                    self._result = (False,)
                else:
                    self._result = (1,)

            def fetchone(self):
                return self._result

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def cursor(self):
                return FakeCursor()

        class FakePsycopg2:
            @staticmethod
            def connect(*_args, **_kwargs):
                return FakeConnection()

        def primary_backend(domain):
            return "sqlite" if domain == "company_orders" else "postgres"

        with mock.patch("app.services.database_status_service.psycopg2", FakePsycopg2), \
             mock.patch("app.services.database_status_service.domain_primary_backend", side_effect=primary_backend), \
             mock.patch("app.services.database_status_service.domain_dual_write_enabled", return_value=False), \
             mock.patch("app.services.database_status_service.domain_validate_enabled", return_value=False):
            payload = get_database_status()
        self.assertEqual("postgres", payload["current_primary"])
        self.assertTrue(payload["postgres"]["connected"])
        self.assertFalse(payload["postgres"]["schema_ready"])
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["safe_mode"])
        self.assertEqual(["company_orders"], payload["summary"]["sqlite_primary_domains"])
        self.assertFalse(payload["summary"]["postgres_primary_complete"])
        self.assertTrue(payload["summary"]["fail_closed"])

    def test_legacy_stream_status_audits_postgres_primary_runtime(self):
        from app.services.legacy_runtime_service import get_legacy_stream_status

        def primary_backend(domain):
            return "sqlite" if domain == "ingest_events" else "postgres"

        with mock.patch("app.services.legacy_runtime_service.postgres_available", return_value=True), \
             mock.patch("app.services.legacy_runtime_service.domain_primary_backend", side_effect=primary_backend), \
             mock.patch("app.services.legacy_runtime_service.collector_status", return_value={"running": False}), \
             mock.patch("app.services.legacy_runtime_service._tiktok_operator_status", return_value={"connected": False}):
            payload = get_legacy_stream_status()
        self.assertFalse(payload["ok"])
        self.assertEqual("postgres_primary_incomplete", payload["database_runtime"]["reason"])
        self.assertEqual(["ingest_events"], payload["database_runtime"]["non_postgres_domains"])
        self.assertTrue(payload["database_runtime"]["fail_closed"])

    def test_deep_runtime_diagnostics_includes_system_payload(self):
        app = create_app(with_runtime=False)
        with mock.patch("app.services.diagnostics_service._fastapi_runtime_payload", return_value={"redis_connected": True}), \
             mock.patch("server.api._build_system_diagnostics", return_value={"ok": True, "stream": {"running": False}}):
            with TestClient(app) as client:
                resp = client.get("/api/v2/diagnostics/runtime/deep")
                self.assertEqual(200, resp.status_code)
                payload = resp.json()
                self.assertEqual("deep", payload["diagnostics_mode"])
                self.assertEqual({"running": False}, payload["stream"])
                self.assertEqual(True, payload["fastapi_runtime"]["redis_connected"])


if __name__ == "__main__":
    unittest.main()
