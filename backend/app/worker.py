"""Celery background worker and scheduler.

Why a queue? Verifying a report calls a vision model (seconds, sometimes rate-limited),
so the upload request returns immediately with status under_verification and the work
happens here. Redis is the message broker.

The scheduler ("beat") triggers the SLA sweep every SLA_SWEEP_INTERVAL_S seconds.

Run:
    celery -A app.worker worker --loglevel=info   # does the work
    celery -A app.worker beat --loglevel=info     # schedules the SLA sweep (run ONE)
"""

import uuid

from celery import Celery

from app.config import get_settings

celery_app = Celery("roadwatch", broker=get_settings().redis_url)
celery_app.conf.update(
    task_acks_late=True,  # if the worker dies mid-task, the task is re-delivered
    worker_prefetch_multiplier=1,
    task_default_queue="roadwatch",
    beat_schedule={
        "sla-sweep": {
            "task": "tickets.sla_sweep",
            "schedule": float(get_settings().sla_sweep_interval_s),
        },
    },
)


@celery_app.task(
    name="reports.verify",
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    max_retries=5,
)
def verify_report_task(report_id: str) -> None:
    from app.reports.service import process_report

    process_report(uuid.UUID(report_id))


@celery_app.task(name="tickets.sla_sweep")
def sla_sweep_task() -> dict:
    from app.tickets.sla import run_sla_sweep

    result = run_sla_sweep()
    return {"warned": len(result.warned), "escalated": len(result.escalated),
            "decided": len(result.decided)}
