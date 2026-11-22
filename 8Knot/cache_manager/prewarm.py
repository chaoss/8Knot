"""Warm configured orgs sequentially, using the browser's registered data tasks."""

import argparse
import logging
import os
from pathlib import Path
import sys
import time

# Support `python3 cache_manager/prewarm.py` from the image's working directory.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


POLL_SECONDS = 2


def parse_orgs(value):
    """Normalize a comma-separated, operator-picked list, preserving its order."""
    return list(dict.fromkeys(org.strip().lower() for org in value.split(",") if org.strip()))


def warm_orgs(orgs, timeout=7200, max_in_flight=4):
    """Warm each org with at most `max_in_flight` tasks outstanding across the whole run.

    Timeout is a per-org deadline in seconds, including queue time and retries.
    A timeout does not cancel its tasks: they keep their slots until they reach a
    terminal state, so later orgs only use the remaining capacity. A failed org
    is logged and skipped; one summary error is raised after every org was tried.
    """
    from cache_manager import cache_facade as cf
    from db_manager.collectoss_manager import CollectOSSManager
    from queries.registry import QUERIES

    manager = CollectOSSManager()
    total = 0
    pending = {}  # job id -> (org, query name, job); queued, running and retrying jobs
    failed_orgs = []

    def reap(org):
        """Release finished jobs; return True if a job of `org` failed."""
        org_failed = False
        for job_id, (job_org, name, job) in list(pending.items()):
            try:
                if not job.ready():
                    continue
                error = None if job.successful() else job.result
            except Exception:
                logging.exception("PREWARM %s %s: cannot read state of %s", job_org, name, job_id)
                continue
            del pending[job_id]
            if error is None:
                logging.info("PREWARM %s %s: completed %s", job_org, name, job_id)
                continue
            logging.error("PREWARM %s %s: task %s failed: %r", job_org, name, job_id, error)
            org_failed = org_failed or job_org == org
        return org_failed

    for org in orgs:
        failed = False
        try:
            manager.get_engine()
            repos = manager.resolve_org_repos([org]).get(org)
            if not repos:
                raise RuntimeError("no repositories found")
            logging.info("PREWARM %s: %d repos, %d queries", org, len(repos), len(QUERIES))
            deadline = time.monotonic() + timeout
            todo = list(QUERIES)
            while True:
                failed = reap(org) or failed
                while todo and len(pending) < max_in_flight:
                    query = todo.pop(0)
                    try:
                        missing = cf.get_uncached(query.__name__, repos)
                        if not missing:
                            logging.info("PREWARM %s %s: NO DISPATCH - ALL REPOS IN CACHE", org, query.__name__)
                            continue
                        job = query.apply_async(args=[missing], queue="data")
                    except Exception:
                        # Stop dispatching, but still wait for what was already submitted.
                        failed = True
                        todo.clear()
                        logging.exception("PREWARM %s %s: dispatch failed", org, query.__name__)
                        break
                    pending[job.id] = (org, query.__name__, job)
                    total += 1
                    logging.info("PREWARM %s %s: dispatched %s (%d repos)", org, query.__name__, job.id, len(missing))
                if not todo and not any(entry[0] == org for entry in pending.values()):
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    failed = True
                    logging.error("PREWARM %s: deadline exceeded with %d queries undispatched", org, len(todo))
                    break
                time.sleep(min(POLL_SECONDS, remaining))
            for query in QUERIES:
                missing = cf.get_uncached(query.__name__, repos)
                if missing:
                    failed = True
                    logging.error("PREWARM %s %s: %d repos still uncached", org, query.__name__, len(missing))
        except Exception:
            failed = True
            logging.exception("PREWARM %s: failed", org)
        if failed:
            failed_orgs.append(org)
        else:
            logging.info("PREWARM %s: verified all query/repo pairs", org)

    if pending:
        logging.error("PREWARM outstanding jobs: %s", sorted(pending))
    if failed_orgs:
        raise RuntimeError(f"PREWARM incomplete for orgs: {', '.join(failed_orgs)}; see errors above")
    logging.info("PREWARM complete: %d orgs, %d tasks dispatched", len(orgs), total)
    return total


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--orgs", default=os.getenv("PREWARM_ORGS", ""), help="Comma-separated orgs (default: PREWARM_ORGS)"
    )
    parser.add_argument("--timeout", type=float, default=7200, help="Per-org timeout in seconds (default: 7200)")
    parser.add_argument("--max-in-flight", type=int, default=4, help="Max outstanding tasks overall (default: 4)")
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.max_in_flight < 1:
        parser.error("--max-in-flight must be a positive integer")
    logging.basicConfig(format="%(asctime)s %(levelname)-8s %(message)s", level=logging.INFO)
    orgs = parse_orgs(args.orgs)
    if not orgs:
        logging.info("PREWARM disabled: PREWARM_ORGS is empty")
        return 0
    try:
        warm_orgs(orgs, timeout=args.timeout, max_in_flight=args.max_in_flight)
    except Exception:
        logging.exception("PREWARM failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
