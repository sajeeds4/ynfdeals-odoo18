import re
from datetime import datetime
from typing import Any

COLLECTOR_SQLITE_RUNTIME_RETIRED = "collector_sqlite_runtime_retired"


class NullConnection:
    """Placeholder used while collector ingest is routed through Postgres cutover helpers."""

    def execute(self, *args, **kwargs):
        raise RuntimeError(COLLECTOR_SQLITE_RUNTIME_RETIRED)

    def executemany(self, *args, **kwargs):
        raise RuntimeError(COLLECTOR_SQLITE_RUNTIME_RETIRED)

    def executescript(self, *args, **kwargs):
        raise RuntimeError(COLLECTOR_SQLITE_RUNTIME_RETIRED)

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


def _is_null_connection(conn) -> bool:
    return isinstance(conn, NullConnection)



_OUR_STREAMER_NAMES = {"ynfdeals"}


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _local_day_key(value: str | None) -> str | None:
    dt = _parse_iso(value)
    if not dt:
        return None
    try:
        return dt.astimezone().date().isoformat()
    except Exception:
        return None


def _extract_stream_slug(stream_url: str | None) -> str | None:
    if not stream_url:
        return None
    match = re.search(r"/live/([^/?#]+)", str(stream_url), flags=re.IGNORECASE)
    if not match:
        return None
    slug = match.group(1).strip().lower()
    return slug or None


def _normalize_stream_identity(stream_url: str | None = None, streamer_name: str | None = None) -> str | None:
    name = (streamer_name or "").strip().lower()
    if name:
        return name
    return _extract_stream_slug(stream_url)


def _merge_stream_rows(conn: Any, source_id: int, target_id: int) -> int:
    try:
        from server.ingest_cutover import merge_ingest_stream_rows

        return int(merge_ingest_stream_rows(conn, int(source_id), int(target_id)))
    except Exception as exc:
        raise RuntimeError(COLLECTOR_SQLITE_RUNTIME_RETIRED) from exc


def get_or_create_spectator_stream(conn: Any, stream_url: str, started_at: str, streamer_name: str | None = None,
                                   title: str | None = None) -> int:
    try:
        from server.ingest_cutover import ensure_ingest_stream

        stream_id = ensure_ingest_stream(stream_url, streamer_name=streamer_name, title=title, started_at=started_at)
        if stream_id:
            return int(stream_id)
    except Exception as exc:
        raise RuntimeError(COLLECTOR_SQLITE_RUNTIME_RETIRED) from exc
    raise RuntimeError(COLLECTOR_SQLITE_RUNTIME_RETIRED)


def finalize_spectator_stream_identity(conn: Any, stream_id: int, stream_url: str,
                                       streamer_name: str | None = None, title: str | None = None) -> int:
    try:
        from server.ingest_cutover import finalize_ingest_stream_identity

        return int(finalize_ingest_stream_identity(conn, int(stream_id), stream_url, streamer_name, title))
    except Exception as exc:
        raise RuntimeError(COLLECTOR_SQLITE_RUNTIME_RETIRED) from exc


def migrate_spectator_streams_to_daily(conn: Any) -> dict:
    raise RuntimeError(COLLECTOR_SQLITE_RUNTIME_RETIRED)


def connect(db_path: str | None, *, postgres_mode: bool = False) -> NullConnection:
    target = str(db_path or "").strip()
    if target:
        raise RuntimeError(COLLECTOR_SQLITE_RUNTIME_RETIRED)
    if not postgres_mode:
        raise RuntimeError("collector_postgres_runtime_required")
    return NullConnection()


def init_db(conn: Any) -> None:
    if _is_null_connection(conn):
        return
    raise RuntimeError(COLLECTOR_SQLITE_RUNTIME_RETIRED)
