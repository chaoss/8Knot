# Minimal Viable DB

A ready-to-use PostgreSQL database, pre-loaded with real collected project data,
so you can run 8Knot — or explore the data from a notebook — **locally, without
access to a remote collectOSS/Augur instance**.

It ships as a published container image, so there's nothing to build and no data
file to supply. `docker compose up` pulls it and it should be ready in seconds.

Image: `ghcr.io/oss-aspen/sample-collected-data:latest`

---

## Quick start

1. Point 8Knot at the local database by setting these values in your `.env`:

   ```
   AUGUR_HOST=sample-collected-data
   AUGUR_PORT=5432
   AUGUR_DATABASE=sample_collected_data
   AUGUR_USERNAME=sample_user
   AUGUR_PASSWORD=sample_password
   AUGUR_SCHEMA=data,augur_data
   ```

2. Start the stack from the top level of the repo:

   ```bash
   podman compose up --build
   ```

8Knot is at http://localhost:8080 and reads from the sample
database. The `sample-collected-data` service pulls the image and starts
instantly (the data is baked in, so there's no import step).

---

## Connecting directly (psql, DBeaver, notebooks)

The database is also exposed on **host port 5433** (mapped from the container's
5432, so it won't clash with a local Postgres):

| Setting  | Value                   |
| -------- | ----------------------- |
| Host     | `localhost`             |
| Port     | `5433`                  |
| Database | `sample_collected_data` |
| User     | `sample_user`           |
| Password | `sample_password`       |

```bash
psql -h localhost -p 5433 -U sample_user -d sample_collected_data
```

Tables live in the **`data`** schema (the collectOSS schema name), so qualify
queries — for example `data.repo`, `data.commits`, `data.pull_requests`.

---

## Notes

- **Self-contained** — no Augur credentials, API keys, or dump files required.
- **Data only** — the image contains just the `data` schema. Augur's operations
  schema (user accounts, tokens, API keys) is deliberately **not** included.
- **Sample, not live** — the data is a fixed snapshot for local development and
  demos, not a continuously updated instance.
