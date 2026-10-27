# Advanced configuration

These optional environment variables can be added to `.env`. The defaults apply
when they are omitted; no changes are needed for initial setup.

## Source database timeouts

Connections to CollectOSS use PostgreSQL timeouts to bound long-running statements
and abandoned transactions:

- `COLLECTOSS_STATEMENT_TIMEOUT_MS`: worker statement timeout, in milliseconds.
  Default: `500000` (500 seconds), below the query worker's 540-second soft limit.
- `COLLECTOSS_ENGINE_STATEMENT_TIMEOUT_MS`: app-server statement timeout, in
  milliseconds. Default: `1800000` (30 minutes), allowing the initial search query
  more time than worker queries.
- `COLLECTOSS_IDLE_TX_TIMEOUT_MS`: maximum idle time inside an open transaction,
  in milliseconds. Default: `120000` (2 minutes). This also applies while a worker
  is writing a batch to the cache between source fetches.

Keep the worker statement timeout below Celery's query-worker soft time limit
when adjusting either setting. PostgreSQL applies this limit per statement,
including individual server-side cursor fetches, rather than to the total task.
Canceled queries are reported as failures without automatic Celery retries.

Both connection paths enable server-side TCP keepalives with a 60-second idle
period, 10-second interval, and three probes. PostgreSQL 14 and newer also check
for disconnected clients during queries every 10 seconds when the database host
supports it. If these checks are unavailable, timeouts still apply.

Closing a browser tab does not disconnect a worker from PostgreSQL. These settings
bound database work and clean up abandoned sessions after an instance disappears;
they do not implement cancellation on browser navigation.

Existing database credential variables retain their `AUGUR_*` names.
