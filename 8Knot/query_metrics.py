"""
Recorder for query timings and search counts (issue #1247).

Off unless METRICS_REDIS_HOST is set. A call only puts an event on a queue;
a daemon thread sends the events to the metrics Redis, so recording never
slows or breaks a request or a Celery task. See docs/specs/query-metrics.md
for the data layout.
"""

import datetime
import logging
import os
import queue
import threading
import time

import redis

# TimeSeries retention and day-key TTL, 30 and 31 days.
RETENTION_MS = 2592000000
DAY_TTL = 2678400
QUEUE_SIZE = 10000
BATCH_SIZE = 500

_lock = threading.Lock()
_queue = None
_pid = None


def timing(stage: str, query: str, seconds: float) -> None:
    """Records that one run of {query}'s {stage} took {seconds} seconds."""
    try:
        if not os.getenv("METRICS_REDIS_HOST"):
            return
        _events().put_nowait(("timing", stage, query, seconds, time.time()))
    except Exception:
        pass


def search(kind: str, name: str) -> None:
    """Records that {name}, a repo URL or org, was searched for."""
    try:
        if not os.getenv("METRICS_REDIS_HOST"):
            return
        _events().put_nowait(("search", kind, name, time.time()))
    except Exception:
        pass


def _events():
    """Returns this process's event queue, starting the writer thread on first use.

    A forked child inherits the parent's queue but not its writer thread, so
    each PID gets its own; the lock is only held while starting the thread.
    """
    global _queue, _pid
    pid = os.getpid()
    if _pid == pid:
        return _queue
    with _lock:
        if _pid != pid:
            events = queue.Queue(maxsize=QUEUE_SIZE)
            threading.Thread(target=_writer, args=(events,), daemon=True).start()
            _queue = events
            _pid = pid
        return _queue


def _writer(events: queue.Queue) -> None:
    """Drains the queue into the metrics Redis. Runs forever; a failed
    batch is dropped and the next one is tried 5 seconds later."""
    client = None
    last_log = 0.0
    while True:
        batch = [events.get()]
        while len(batch) <= BATCH_SIZE:
            try:
                batch.append(events.get_nowait())
            except queue.Empty:
                break
        try:
            # created here, not above the loop, so that a bad host/port
            # config is dropped-and-warned like any other failure instead
            # of killing the writer thread
            if client is None:
                client = redis.StrictRedis(
                    host=os.getenv("METRICS_REDIS_HOST"),
                    port=int(os.getenv("METRICS_REDIS_PORT", "6379")),
                    password=os.getenv("REDIS_PASSWORD", ""),
                    socket_connect_timeout=1,
                    socket_timeout=1,
                )
            pipe = client.pipeline(transaction=False)
            kinds = set()
            for event in batch:
                if event[0] == "timing":
                    _, stage, query, seconds, at = event
                    pipe.execute_command(
                        "TS.ADD",
                        f"km:t:{stage}:{query}",
                        int(at * 1000),
                        seconds,
                        "RETENTION",
                        RETENTION_MS,
                        "ON_DUPLICATE",
                        "MAX",
                        "LABELS",
                        "stage",
                        stage,
                        "query",
                        query,
                    )
                else:
                    _, kind, name, at = event
                    day = datetime.datetime.fromtimestamp(at, tz=datetime.timezone.utc).strftime("%Y%m%d")
                    pipe.zincrby(f"km:search:{kind}:all", 1, name)
                    pipe.zincrby(f"km:search:{kind}:day:{day}", 1, name)
                    pipe.expire(f"km:search:{kind}:day:{day}", DAY_TTL)
                    kinds.add(kind)
            # rebuild the 30-day union once per batch and kind
            for kind in kinds:
                today = datetime.datetime.now(tz=datetime.timezone.utc)
                day_keys = [
                    f"km:search:{kind}:day:{(today - datetime.timedelta(days=back)).strftime('%Y%m%d')}"
                    for back in range(30)
                ]
                pipe.zunionstore(f"km:search:{kind}:30d", day_keys)
            pipe.execute()
        except Exception as error:
            now = time.time()
            if now - last_log >= 60:
                last_log = now
                logging.warning(f"query_metrics: dropped {len(batch)} events: {error}")
            time.sleep(5)
