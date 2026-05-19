from app.core.task_runtime import run_tracked_task
from app.workers.celery_app import celery_app
from app.services.ingest_service import list_failed_ingests, replay_failed_ingest, resolve_failed_ingest
from server.events_db import backfill_users_and_lots


@celery_app.task(name="app.tasks.ingest.replay_failed_ingest")
def task_replay_failed_ingest(failed_id: int):
    return run_tracked_task(f"replay_failed_ingest:{int(failed_id)}", replay_failed_ingest, failed_id, lock_ttl_seconds=300)


@celery_app.task(name="app.tasks.ingest.resolve_failed_ingest")
def task_resolve_failed_ingest(failed_id: int):
    return run_tracked_task(f"resolve_failed_ingest:{int(failed_id)}", resolve_failed_ingest, failed_id, lock_ttl_seconds=300)


@celery_app.task(name="app.tasks.ingest.list_failed_ingests")
def task_list_failed_ingests(include_resolved: bool = False):
    def _run():
        return {"ok": True, "rows": list_failed_ingests(include_resolved=include_resolved)}
    return run_tracked_task("list_failed_ingests", _run, lock_ttl_seconds=60)


@celery_app.task(name="app.tasks.ingest.backfill_users_and_lots")
def task_backfill_users_and_lots(stream_id: int | None = None):
    def _run():
        backfill_users_and_lots(stream_id=stream_id)
        return {"ok": True, "stream_id": stream_id}
    suffix = "all" if stream_id is None else str(int(stream_id))
    return run_tracked_task(f"backfill_users_and_lots:{suffix}", _run, lock_ttl_seconds=1800)
