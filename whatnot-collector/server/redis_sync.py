"""
Optional Redis sync service.

This module mirrors important app state into Redis, but it is intentionally
side-effect free unless REDIS_ENABLED is turned on and the caller invokes it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .company_db import (
    get_company_session,
    get_mega_dashboard_summary,
    inventory_summary,
    list_auction_results,
    list_company_sessions,
    list_pending_winner_assignments,
)
from .redis_sidecar import RedisSidecar, get_redis_sidecar
from .state import load_collector_state, load_shared_scan_state


@dataclass
class RedisSyncResult:
    key: str
    written: bool
    count: int = 0


class RedisSyncService:
    def __init__(
        self,
        sidecar: RedisSidecar | None = None,
        *,
        load_collector_state_fn=load_collector_state,
        load_shared_scan_state_fn=load_shared_scan_state,
        list_company_sessions_fn=list_company_sessions,
        get_company_session_fn=get_company_session,
        list_pending_winner_assignments_fn=list_pending_winner_assignments,
        list_auction_results_fn=list_auction_results,
        get_mega_dashboard_summary_fn=get_mega_dashboard_summary,
        inventory_summary_fn=inventory_summary,
    ):
        self.sidecar = sidecar or get_redis_sidecar()
        self.load_collector_state_fn = load_collector_state_fn
        self.load_shared_scan_state_fn = load_shared_scan_state_fn
        self.list_company_sessions_fn = list_company_sessions_fn
        self.get_company_session_fn = get_company_session_fn
        self.list_pending_winner_assignments_fn = list_pending_winner_assignments_fn
        self.list_auction_results_fn = list_auction_results_fn
        self.get_mega_dashboard_summary_fn = get_mega_dashboard_summary_fn
        self.inventory_summary_fn = inventory_summary_fn

    def _write_snapshot(self, key: str, payload, *, ttl_sec: int | None = None) -> RedisSyncResult:
        written = self.sidecar.set_json(key, payload, ttl_sec=ttl_sec)
        count = 0
        if isinstance(payload, list):
            count = len(payload)
        elif isinstance(payload, dict) and isinstance(payload.get("rows"), list):
            count = len(payload["rows"])
        elif payload:
            count = 1
        return RedisSyncResult(key=key, written=written, count=count)

    def sync_collector_state(self) -> RedisSyncResult:
        state = self.load_collector_state_fn() or {}
        return self._write_snapshot("sync:collector_state", state, ttl_sec=30)

    def sync_shared_scan_state(self) -> RedisSyncResult:
        state = self.load_shared_scan_state_fn() or {}
        return self._write_snapshot("sync:shared_scan_state", state, ttl_sec=30)

    def sync_sessions(self, *, account: str = "ynfdeals", limit: int = 100) -> RedisSyncResult:
        rows = self.list_company_sessions_fn(account, limit=int(limit))
        payload = {
            "account": account,
            "rows": rows,
        }
        return self._write_snapshot(f"sync:sessions:{account}", payload, ttl_sec=30)

    def sync_session_detail(self, session_id: int) -> RedisSyncResult:
        session = self.get_company_session_fn(int(session_id))
        payload = session or {}
        return self._write_snapshot(f"sync:session:{int(session_id)}", payload, ttl_sec=30)

    def sync_pending_winners(self, session_id: int, statuses=None, limit: int = 250) -> RedisSyncResult:
        rows = self.list_pending_winner_assignments_fn(int(session_id), statuses=statuses, limit=int(limit))
        payload = {
            "session_id": int(session_id),
            "statuses": list(statuses) if statuses else None,
            "rows": rows,
        }
        return self._write_snapshot(f"sync:pending_winners:{int(session_id)}", payload, ttl_sec=15)

    def sync_auction_results(self, session_id: int, limit: int = 250) -> RedisSyncResult:
        rows = self.list_auction_results_fn(session_id=int(session_id), limit=int(limit))
        payload = {
            "session_id": int(session_id),
            "rows": rows,
        }
        return self._write_snapshot(f"sync:auction_results:{int(session_id)}", payload, ttl_sec=30)

    def sync_overview_summary(self) -> RedisSyncResult:
        payload = self.get_mega_dashboard_summary_fn() or {}
        return self._write_snapshot("sync:overview_summary", payload, ttl_sec=30)

    def sync_inventory_summary(self) -> RedisSyncResult:
        payload = self.inventory_summary_fn() or {}
        return self._write_snapshot("sync:inventory_summary", payload, ttl_sec=30)

    def sync_job_state(self, payload: dict | None = None) -> RedisSyncResult:
        state = payload or {}
        return self._write_snapshot("sync:job_state", state, ttl_sec=30)

    def sync_locks_state(self, payload: dict | None = None) -> RedisSyncResult:
        state = payload or {}
        return self._write_snapshot("sync:locks_state", state, ttl_sec=15)

    def sync_live_bundle(
        self,
        *,
        account: str = "ynfdeals",
        session_limit: int = 50,
        job_state: dict | None = None,
        locks_state: dict | None = None,
    ) -> list[RedisSyncResult]:
        results = [
            self.sync_collector_state(),
            self.sync_shared_scan_state(),
            self.sync_sessions(account=account, limit=session_limit),
            self.sync_overview_summary(),
            self.sync_inventory_summary(),
            self.sync_job_state(job_state),
            self.sync_locks_state(locks_state),
        ]
        sessions = self.list_company_sessions_fn(account, limit=max(1, int(session_limit)))
        active = None
        for row in sessions:
            status = str(row.get("status") or "").lower()
            if status in {"live", "open", "draft"}:
                active = row
                break
        if active and active.get("id"):
            session_id = int(active["id"])
            results.append(self.sync_session_detail(session_id))
            results.append(self.sync_pending_winners(session_id, statuses=("pending", "assigned", "needs_review", "confirmed")))
            results.append(self.sync_auction_results(session_id))
        return results

    def publish_event(self, channel: str, payload) -> bool:
        return self.sidecar.publish_json(f"sync_event:{channel}", payload)

    def append_event(self, stream_name: str, payload, *, maxlen: int = 1000) -> str | None:
        return self.sidecar.append_stream_json(f"sync_event:{stream_name}", payload, maxlen=maxlen)


def get_redis_sync_service() -> RedisSyncService:
    return RedisSyncService()
