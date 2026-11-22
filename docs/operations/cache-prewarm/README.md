# Cache pre-warming

Pre-warming fills the query cache for a hand-picked list of orgs **after all
source materialized-view refreshes succeed and the cache has been reset**, so a
user's first selection of a warmed org dispatches no collection jobs. It is
**off by default**.

Warming uses the same 16 data tasks as browser search (`queries/registry.py`).
For each org it submits only missing query/repo pairs to the `data` queue, waits
for them (including Celery retries), then checks `get_uncached` for every query.

## Configuration

`PREWARM_ORGS` is empty in `.env.sample`; empty/unset disables warming, and a
disabled run needs no database credentials. Example list, not a traffic ranking:

```dotenv
PREWARM_ORGS=kubernetes,apache,kubeflow,ansible
```

Names are case-insensitive and deduplicated. Orgs are resolved with
`CollectOSSManager.resolve_org_repos([org])`, so the worker needs the `AUGUR_*`
source credentials; an unknown org or one with no repos is an org failure.
Recreate the worker containers after changing their `.env`.

```sh
docker compose exec -T worker-query python3 cache_manager/prewarm.py
docker compose exec -T -e PREWARM_ORGS=kubernetes,apache \
  worker-query python3 cache_manager/prewarm.py
```

Options: `--orgs` overrides the environment; `--timeout` (default 7200 s) is the
per-org deadline including queue time and retries; `--max-in-flight` (default 4)
is the cap on outstanding tasks for the whole run, leaving 12 of the 16
production data slots free for browser traffic.

## Failure and timeout semantics

- Queued, running and retrying tasks each occupy one of the `--max-in-flight`
  slots until they reach a terminal state. A Celery RETRY does not release it.
- A timeout does not cancel a task. Unfinished tasks stay in the run-wide
  pending set and keep their slots while later orgs run on the remaining
  capacity. If every slot stays occupied until an org's deadline, that org fails
  and the run continues.
- Resolution, dispatch, task, timeout and coverage failures are logged per org
  (org, query, task id). Already-submitted work of that org is awaited, then the
  next org starts. After all orgs were tried the command exits **1 if any org
  failed** (outstanding task ids are logged), otherwise 0.
- Successful work stays cached, so a rerun only dispatches what is missing.
- The wait deadline is not a database cancellation mechanism; worker
  soft/hard limits (540/600 s) and source statement timeouts still apply.
- Separate warm commands each have their own cap; the deployment guard against
  launching the same job twice prevents accidental duplication.

## Refreshed-cache workflow

1. Refresh all source materialized views (any failure stops the sequence).
2. Reset the cache tables and bookkeeping in one transaction.
3. Run the warm command; only exit 0 with a `verified all query/repo pairs` line
   per org means success.

The reset runs after **every** successful refresh, even with warming disabled,
so each refresh leaves a fully cold cache. It retries for about 12.5 minutes and
fails visibly (warming skipped) if continuous big-org load keeps it from the
lock. Users mid-load may briefly see empty charts once while data is recollected.

Steps 2–3 and the cache lock-capacity setting are deployed by the infra-ansible
change (separate PR/runbook; not part of this repository). Warm only on images
that include `cache_manager/prewarm.py` on every worker, and never inside
`db_init` or between individual view refreshes. Collection safety for browser/warm
overlap comes from the per-repo claims in `cache_facade.caching_wrapper`.

## Verification

Mocked scheduling tests, plus the real bulk resolver on a throwaway PostgreSQL
(set `QUERY_TEST_DSN` to a **test-only** database):

```sh
QUERY_TEST_DSN='host=127.0.0.1 port=5432 dbname=prewarm_test user=postgres password=test' \
  uv run pytest -q tests/test_prewarm.py tests/test_search_options.py
```

Full-stack acceptance needs a deployed image, populated CollectOSS, broker and
completed refreshes, and was not run locally. On staging after a planned reset:
run the warm command (exit 0, a verified line per org); rerun it (`0 tasks
dispatched`); then select each warmed org in a fresh browser session and expect
`NO DISPATCH - ALL REPOS IN CACHE` for all 16 queries.
