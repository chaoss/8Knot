from celery import Celery, Task
from celery.signals import task_postrun, task_prerun
from dash import CeleryManager
from psycopg2.errors import QueryCanceled
import os
import time

import query_metrics

redis_host = "{}".format(os.getenv("REDIS_SERVICE_HOST", "redis-broker"))
redis_port = "{}".format(os.getenv("REDIS_SERVICE_PORT", "6379"))
redis_password = "{}@".format(os.getenv("REDIS_PASSWORD", ""))
REDIS_URL = f"redis://:{redis_password}{redis_host}:{redis_port}"


"""CREATE CELERY TASK QUEUE AND MANAGER"""


class EightKnotTask(Task):
    """Base task that does not retry deterministic database cancellations."""

    dont_autoretry_for = (QueryCanceled,)


celery_app = Celery(
    __name__,
    broker=REDIS_URL,
    backend=REDIS_URL,
    task_cls=EightKnotTask,
)

celery_app.conf.update(
    task_time_limit=2700,  # 45 minutes
    task_acks_late=True,
    task_track_started=True,
    result_extended=True,
    worker_prefetch_multiplier=1,
)

celery_manager = CeleryManager(celery_app=celery_app)


"""QUERY METRICS SIGNALS
Tasks dispatched with a km_sent header (index_callbacks.run_queries) record
dispatch-to-start (queue_wait) and dispatch-to-success (e2e); tasks without
it, like background callbacks and user_groups_query, are ignored."""


@task_prerun.connect
def _record_queue_wait(task=None, **kwargs):
    if (km_sent := getattr(task.request, "km_sent", None)) is not None and task.request.retries == 0:
        query_metrics.timing("queue_wait", task.name.rsplit(".", 1)[-1], time.time() - km_sent)


@task_postrun.connect
def _record_e2e(task=None, state=None, **kwargs):
    km_sent = getattr(task.request, "km_sent", None)
    if km_sent is not None and state == "SUCCESS":
        query_metrics.timing("e2e", task.name.rsplit(".", 1)[-1], time.time() - km_sent)
