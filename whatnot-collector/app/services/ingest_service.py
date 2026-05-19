from server.events_db import get_failed_ingests, increment_retry_count, mark_failed_ingest_resolved


def replay_failed_ingest(failed_id: int):
    increment_retry_count(failed_id)
    return {"ok": True, "failed_id": failed_id}


def resolve_failed_ingest(failed_id: int):
    mark_failed_ingest_resolved(failed_id)
    return {"ok": True, "failed_id": failed_id}


def list_failed_ingests(include_resolved: bool = False):
    return get_failed_ingests(include_resolved=include_resolved)

