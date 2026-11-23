#!/bin/sh
# Prints Redis commands for fake query-metrics data (24h of timings, a few searches).
# Usage: sh scripts/seed_query_metrics.sh | docker compose exec -T redis-metrics redis-cli -a "$REDIS_PASSWORD" --no-auth-warning
day=$(date -u +%Y%m%d)
awk -v now="$(date +%s)" -v day="$day" 'BEGIN {
  srand(1247)
  ns = split("queue_wait augur_sql cache_write e2e cache_read", stages, " ")
  nq = split("commits_query prs_query issues_query affiliation_query", queries, " ")
  for (s = 1; s <= ns; s++) for (q = 1; q <= nq; q++) for (i = 0; i < 288; i++)
    printf "TS.ADD km:t:%s:%s %d000 %.4f RETENTION 2592000000 ON_DUPLICATE MAX LABELS stage %s query %s\n", \
      stages[s], queries[q], now - i * 300, 0.05 + rand() * q * s, stages[s], queries[q]
  nr = split("https://github.com/chaoss/augur https://github.com/chaoss/8knot https://github.com/chaoss/grimoirelab https://github.com/kubernetes/kubernetes https://github.com/ansible/ansible", repos, " ")
  for (r = 1; r <= nr; r++) {
    printf "ZINCRBY km:search:repo:all %d %s\n", (nr - r + 1) * 21, repos[r]
    printf "ZINCRBY km:search:repo:day:%s %d %s\n", day, (nr - r + 1) * 7, repos[r]
  }
  no = split("chaoss kubernetes ansible", orgs, " ")
  for (o = 1; o <= no; o++) {
    printf "ZINCRBY km:search:org:all %d %s\n", (no - o + 1) * 15, orgs[o]
    printf "ZINCRBY km:search:org:day:%s %d %s\n", day, (no - o + 1) * 5, orgs[o]
  }
  split("repo org", kinds, " ")
  for (k = 1; k <= 2; k++) {
    printf "EXPIRE km:search:%s:day:%s 2678400\n", kinds[k], day
    printf "ZUNIONSTORE km:search:%s:30d 1 km:search:%s:day:%s\n", kinds[k], kinds[k], day
  }
}'
