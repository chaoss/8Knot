# Query Metrics

8Knot can record query pipeline timings and top searched repos and orgs in a dedicated Redis instance (`redis-metrics`) and display them in a provisioned Grafana dashboard.

Recording is off by default when `METRICS_REDIS_HOST` is unset.

## Local setup

1. Add these lines to `.env` (alongside your existing `REDIS_PASSWORD`):

   ```dotenv
   METRICS_REDIS_HOST=redis-metrics
   GF_SECURITY_ADMIN_PASSWORD=change-me
   ```

2. Start the stack with the `metrics` profile:

   ```sh
   docker compose --profile metrics up -d
   ```

3. Open `http://localhost:3000` (bound to `127.0.0.1:3000` only; anonymous access and sign-up are disabled), log in as `admin` with `GF_SECURITY_ADMIN_PASSWORD`, and open the **8Knot query metrics** dashboard.

To populate synthetic data for local testing without waiting for live queries, run:

```sh
sh scripts/seed_query_metrics.sh | docker compose exec -T redis-metrics redis-cli -a "$REDIS_PASSWORD" --no-auth-warning
```

## Production setup and access

Production runs `redis-metrics` and `grafana` via `oss-aspen/infra-ansible` (`roles/eightknot`), which enables both services in its compose template without a profile and mounts the provisioned Grafana files from the cloned repository.

1. Add `vault_grafana_admin_password` to the encrypted `vars/secrets.yml` in `oss-aspen/infra-ansible` (`roles/eightknot`).
2. Deploy the `roles/eightknot` changes after releasing the matching 8Knot image.
3. Grafana remains bound to `127.0.0.1:3000` on the EC2 host. Access it over an SSH tunnel:

   ```sh
   ssh -L 3000:127.0.0.1:3000 <ec2-host>
   ```

   Then open `http://localhost:3000` in your local browser and log in as `admin`.

Grafana reads the provisioned data source and dashboard only when it starts, so after a release that changes files under `grafana/`, run `docker compose restart grafana` on the EC2 host.

`redis-metrics` mounts a persistent `redis-metrics` volume and runs with `--save 300 1` so search counts survive container restarts. Memory is capped at 256 MB (`noeviction`) and timing series expire after 30 days.

Public exposure of Grafana, TLS, Caddy routes, and the `openshift/` manifests are out of scope.

## Pipeline stages

Timing samples are stored as Redis TimeSeries keys (`km:t:<stage>:<query>`) in seconds, labeled with `stage` and `query`.

| Stage | Process | Meaning |
| --- | --- | --- |
| `queue_wait` | `worker-query` | Dispatch in `run_queries()` until the task starts (first attempt only) |
| `augur_sql` | `worker-query` | Source database time: `exec_driver_sql()` plus every `fetchmany()` |
| `cache_write` | `worker-query` | PostgreSQL cache time: every row insert, the bookkeeping insert, and the commit |
| `e2e` | `worker-query` | Dispatch in `run_queries()` until the task succeeds, retries included |
| `cache_read` | `app-server` and `worker-callback` | One `retrieve_from_cache()` call |

The dashboard shows a 5-minute average/max trend and a per-query `p50` / `p95` / `max` / `count` summary table over the selected time range (default: last 24 hours) for each stage.

## Top searched repos and orgs

Search counts are stored in Redis sorted sets:

- All time: `km:search:repo:all`, `km:search:org:all`
- Per UTC day (31-day TTL): `km:search:repo:day:<YYYYMMDD>`, `km:search:org:day:<YYYYMMDD>`
- Last 30 UTC days: `km:search:repo:30d`, `km:search:org:30d`

### 30-day window lag

The `30d` keys are rebuilt with `ZUNIONSTORE` over the last 30 UTC day keys each time a search is written. If nobody searches, those keys are not rebuilt and can lag by the time elapsed since the last search. A consumer that requires an exact 30-day window should compute the union of the last 30 `km:search:<kind>:day:<YYYYMMDD>` keys directly.

### Reading top lists for pre-warm

To read the top `N` repos or orgs (returned with the highest score last), run `ZRANGE` with `WITHSCORES`:

```sh
docker compose exec -T redis-metrics redis-cli -a "$REDIS_PASSWORD" --no-auth-warning \
  ZRANGE km:search:repo:30d -15 -1 WITHSCORES

docker compose exec -T redis-metrics redis-cli -a "$REDIS_PASSWORD" --no-auth-warning \
  ZRANGE km:search:org:30d -15 -1 WITHSCORES
```

Substitute `:all` for `:30d` to read all-time counts. A pre-warm job can resolve repo URLs and org names with `augur.repo_git_to_id(url)` and `augur.org_to_repos(org)`.
