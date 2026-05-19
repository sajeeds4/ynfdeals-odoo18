from app.core.task_runtime import run_tracked_task
from app.workers.celery_app import celery_app
from app.services.analytics_service import refresh_recent_stream_facts
from server.reconciler import materialize_stream_facts, materialize_stream_intelligence


@celery_app.task(name="app.tasks.analytics.refresh_recent_stream_facts")
def task_refresh_recent_stream_facts(stream_id: int):
    return run_tracked_task(
        f"refresh_recent_stream_facts:{int(stream_id)}",
        refresh_recent_stream_facts,
        stream_id,
        lock_ttl_seconds=600,
    )


@celery_app.task(name="app.tasks.analytics.materialize_stream_facts")
def task_materialize_stream_facts(stream_id: int):
    def _run():
        materialize_stream_facts(stream_id)
        return {"ok": True, "stream_id": stream_id}
    return run_tracked_task(f"materialize_stream_facts:{int(stream_id)}", _run, lock_ttl_seconds=900)


@celery_app.task(name="app.tasks.analytics.materialize_stream_intelligence")
def task_materialize_stream_intelligence(stream_id: int):
    def _run():
        materialize_stream_intelligence(stream_id)
        return {"ok": True, "stream_id": stream_id}
    return run_tracked_task(f"materialize_stream_intelligence:{int(stream_id)}", _run, lock_ttl_seconds=900)
