from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "whatnot_runtime",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.analytics_tasks",
        "app.tasks.business_tasks",
        "app.tasks.default_tasks",
        "app.tasks.ingest_tasks",
    ],
)

celery_app.conf.update(
    task_default_queue=settings.celery_default_queue,
    task_routes={
        "app.tasks.analytics.*": {"queue": settings.celery_analytics_queue},
        "app.tasks.business.*": {"queue": settings.celery_business_queue},
        "app.tasks.ingest.*": {"queue": settings.celery_ingest_queue},
        "app.tasks.default.*": {"queue": settings.celery_default_queue},
    },
    timezone="America/New_York",
    task_track_started=True,
    task_ignore_result=True,
    task_store_errors_even_if_ignored=True,
)

celery_app.autodiscover_tasks(["app.tasks"])
