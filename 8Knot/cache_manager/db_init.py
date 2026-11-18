"""
NOTES ABOUT THIS FILE:

This file uses raw SQL to create tables in Postgres.
It's typically easiest and best-practice to use a db migration
tool instead of doing error-prone manual administration like this.

Tables are still defined as raw CREATE UNLOGGED TABLE IF NOT EXISTS blocks
below, so adding a table only takes SQL.

Those blocks can't change a table that already exists, so changes to
existing tables are alembic migrations (migrations/), applied on boot. The
CREATE blocks define a fresh cache and migrations upgrade existing ones,
the groundwork for a persistent cache. Migrations are hand-written raw SQL.

Existing caches start from the current schema, including issues_query.labels.
Migration history starts empty; the first schema change gets revision 1.
"""

"""
TABLE_CREATION_INSTRUCTIONS:

For data that we retrieve from Postgres to be cached, we need
to define the "schema" for the table where it will be stored.

Take a moment to look at the correspondence between the table
"commits_query" in this file and the SQL that we have the database
execute, defined in "queries/commits_query.py." Notice that each
of the columns referenced in the SELECT statement has a
corresponding column in the table schema defined below, with a
type that matches the datatype we expect to receive from Augur.

Note also that we use the table creation syntax:
CREATE UNLOGGED TABLE IF NOT EXISTS <name>

We configure the tables to be unlogged to maximize write-to speed.
We can always repopulate a table with minimal inconvenience if
the cache database is destroyed, so we don't need the durability
guarantees of a logged table.

We also only create a new table if a table of the same name
does not already exist. This initialization script ALWAYS runs
on app startup to make sure that the schema of the databse is
intact between application restarts.

To add a new table to the cache, simply copy an existing table
creation block from those below. Given that you're creating a table
for a query in the 'queries/' folder, name the table the same name
as the query function. Name the columns of the table, and give their
types, and everything should work!

To change an existing table (add/drop/rename a column, change a type), add
an alembic migration:

    cd 8Knot/cache_manager
    alembic revision -m "describe change"   # assigns the next numeric revision

Write upgrade()/downgrade() as raw SQL with op.execute(...), and update the
CREATE block too so fresh caches match. Migrations run on every boot. Never
edit a shipped migration; add a new one.

_ensure_repo_id_indexes() is not a migration: CREATE INDEX IF NOT EXISTS is
safe to re-run, so it runs on every boot.

Here's a list of types that postgres defines:
https://www.postgresql.org/docs/current/datatype.html

Generally, 'int' is good for integers,
'float4' is good for normal floats,
'float8' is good for larger precision floats,
'text' is best for text strings.
    - why we aren't using 'varchar':
    https://wiki.postgresql.org/wiki/Don%27t_Do_This#Don.27t_use_varchar.28n.29_by_default
"""

import logging
import os
import sys
import time

import psycopg2 as pg
import redis
from alembic import command
from alembic.config import Config
from psycopg2 import sql as pg_sql


def _env_int(var: str, default: int) -> int:
    """Parse an environment variable as an integer with safe fallback.

    Wraps int() conversion in a try/except so that misconfigured
    environment variables never crash the application on startup.

    Behavior:
        - Env var is unset or empty  -> returns *default*.
        - Env var is a valid integer -> returns int(value).
        - Env var is non-numeric (e.g. "ABCD") -> the string is truthy
          so int() is attempted, raises ValueError, which is caught;
          logs a warning so the misconfiguration is visible and falls
          back to *default*.

    Args:
        var:     Name of the environment variable.
        default: Value returned when the variable is absent, empty,
                 or cannot be parsed as an integer.

    Returns:
        The parsed integer, or *default* on any failure.
    """
    raw = os.getenv(var, "")
    try:
        return int(raw) if raw else default
    except ValueError:
        logging.warning(f"db_init: ignoring non-numeric {var}={raw!r}, using {default}")
        return default


# doesn't use relative import syntax "import .cx_common" because
# cx_common is a neighbor of script, thus is available in PYTHON_PATH
from cx_common import cache_cx_string, env_dbname, init_cx_string


def _connect_with_retry(connection_string, max_retries=5, retry_delay=3):
    """
    Attempt to connect to the database with retries.
    Args:
        connection_string: The connection string to use
        max_retries: Maximum number of retry attempts
        retry_delay: Seconds to wait between retries
    Returns:
        PostgreSQL connection object or None if failed after retries
    """
    retries = 0
    last_exception = None
    while retries < max_retries:
        try:
            logging.warning(f"Attempting database connection (attempt {retries+1}/{max_retries})...")
            conn = pg.connect(connection_string)
            logging.warning("Database connection established successfully!")
            return conn
        except Exception as e:
            last_exception = e
            retries += 1
            if retries < max_retries:
                logging.warning(f"Connection failed: {e}. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logging.critical(f"Failed to connect after {max_retries} attempts: {e}")
    # If we reached here, all connection attempts failed
    raise last_exception


def _create_application_database() -> None:
    """
    On fresh application boot, Postgres is fresh, so
    database where we cache data from Augur isn't configured.

    This function creates the 'augur_cache' database, which will
    contain all of the tables where we'll cache data for visualization.

    Uses CACHE_DB_NAME.
    """

    # Connect to the dbms at top-level
    # to instantiate application db
    # we'll always connect to root-level DB
    # with these creds so they don't need to be
    # parameterized.
    conn = _connect_with_retry(init_cx_string)

    # required so that we can create a database
    conn.autocommit = True

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", (env_dbname,))
            if not cur.fetchone():
                logging.warning(f"CREATING {env_dbname} DATABASE")
                cur.execute(pg_sql.SQL("CREATE DATABASE {}").format(pg_sql.Identifier(env_dbname)))
    finally:
        conn.close()


def _create_application_tables() -> None:
    """
    Creates tables for cached data in 'augur_cache' database.

    Tables created:
        - commits
        - cache_bookkeeping
    """
    # TODO: timestamps being stored as strings- don't need to do that anymore.

    # connect to application database
    conn = _connect_with_retry(cache_cx_string)

    with conn.cursor() as cur:
        # create tables if they don't already exist.
        # TODO: id->repo_id, commits->commit_id
        cur.execute(
            """
            CREATE UNLOGGED TABLE IF NOT EXISTS commits_query(
                repo_id int,
                commit_hash text, -- this is the commit hash, so it's base64 hash.
                author_email text,
                author_date text,
                author_timestamp text,
                committer_timestamp text)
            """
        )
        logging.warning("CREATED commits TABLE")

        cur.execute(
            """
            CREATE UNLOGGED TABLE IF NOT EXISTS issues_query(
                repo_id bigint,
                repo_name text,
                issue bigint,
                issue_number bigint,
                gh_issue bigint,
                reporter_id text,
                issue_closer text,
                created_at text,
                closed_at text,
                labels text
            )
            """
        )
        logging.warning("CREATED issues TABLE")

        cur.execute(
            """
            CREATE UNLOGGED TABLE IF NOT EXISTS prs_query(
                repo_id int,
                repo_name text,
                pull_request_id int,
                pr_src_number int,
                cntrb_id text,
                created_at text,
                closed_at text,
                merged_at text,
                merger_cntrb_id text
            )
            """
        )
        logging.warning("CREATED prs TABLE")

        cur.execute(
            """
            CREATE UNLOGGED TABLE IF NOT EXISTS affiliation_query(
                cntrb_id text,
                created_at text,
                repo_id int,
                login text,
                action text,
                cntrb_company text,
                email_list text
            )
            """
        )
        logging.warning("CREATED affiliation_query TABLE")

        cur.execute(
            """
            CREATE UNLOGGED TABLE IF NOT EXISTS contributors_query(
                repo_id int,
                repo_name text,
                cntrb_id text,
                created_at text,
                login text,
                action text
            )
            """
        )
        logging.warning("CREATED contributors TABLE")

        cur.execute(
            """
            CREATE UNLOGGED TABLE IF NOT EXISTS issue_assignee_query(
                issue_id text,
                repo_id int,
                created_at text,
                closed_at text,
                assign_date text,
                assignment_action text,
                assignee text
            )
            """
        )
        logging.warning("CREATED issue_assignments TABLE")

        cur.execute(
            """
            CREATE UNLOGGED TABLE IF NOT EXISTS pr_assignee_query(
                pull_request_id int,
                repo_id int,
                created_at text,
                closed_at text,
                assign_date text,
                assignment_action text,
                assignee text
            )
            """
        )
        logging.warning("CREATED pr_assignments TABLE")

        # Codebase page tables - enabled for heatmap visualizations
        cur.execute(
            """
            CREATE UNLOGGED TABLE IF NOT EXISTS cntrb_per_file_query(
                repo_id int,
                file_path text,
                cntrb_ids text,
                reviewer_ids text
            )
            """
        )
        logging.warning("CREATED cntrb_per_file_query TABLE")

        cur.execute(
            """
            CREATE UNLOGGED TABLE IF NOT EXISTS pr_file_query(
                file_path text,
                pull_request int,
                repo_id int
            )
            """
        )
        logging.warning("CREATED pr_file_query TABLE")

        cur.execute(
            """
            CREATE UNLOGGED TABLE IF NOT EXISTS repo_files_query(
                repo_id int,
                repo_name text,
                repo_path text,
                rl_analysis_date text,
                file_path text,
                file_name text
            )
            """
        )
        logging.warning("CREATED repo_files_query TABLE")

        cur.execute(
            """
            CREATE UNLOGGED TABLE IF NOT EXISTS repo_languages_query(
                repo_id int,
                programming_language text,
                code_lines int,
                files int
            )
            """
        )
        logging.warning("CREATED repo_languages_query TABLE")

        cur.execute(
            """
            CREATE UNLOGGED TABLE IF NOT EXISTS package_version_query(
                repo_id int,
                name text,
                current_release_date text,
                latest_release_date text,
                libyear float4,
                dep_age text
            )
            """
        )
        logging.warning("CREATED package_version_query TABLE")

        cur.execute(
            """
            CREATE UNLOGGED TABLE IF NOT EXISTS repo_releases_query(
                repo_id int,
                release_name text,
                release_created_at text,
                release_published_at text,
                release_updated_at text
            )
            """
        )
        logging.warning("CREATED repo_releases_query TABLE")

        cur.execute(
            """
            CREATE UNLOGGED TABLE IF NOT EXISTS ossf_score_query(
                repo_id int,
                name text,
                score float4,
                data_collection_date timestamp
            )
            """
        )
        logging.warning("CREATED ossf_score_query TABLE")

        cur.execute(
            """
            CREATE UNLOGGED TABLE IF NOT EXISTS repo_info_query(
                repo_id int,
                issues_enabled text,
                fork_count int,
                watchers_count int,
                license text,
                stars_count int,
                code_of_conduct_file text,
                security_issue_file text,
                security_audit_file text,
                data_collection_date timestamp
            )
            """
        )
        logging.warning("CREATED repo_info_query TABLE")

        cur.execute(
            """
            CREATE UNLOGGED TABLE IF NOT EXISTS pr_response_query(
                pull_request_id int,
                repo_id int,
                cntrb_id text,
                msg_timestamp text,
                msg_cntrb_id text,
                pr_created_at text,
                pr_closed_at text
            )
            """
        )
        logging.warning("CREATED pr_response_query TABLE")

        cur.execute(
            """
            CREATE UNLOGGED TABLE IF NOT EXISTS cache_bookkeeping(
                cache_func text,
                repo_id int,
                ts_cached timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        logging.warning("CREATED cache_bookkeeping TABLE")

        # commit changes, all-or-nothing.
        conn.commit()

    logging.warning("ALL TABLES COMMITTED SUCCESSFULLY")


def _ensure_repo_id_indexes() -> None:
    """Index repo_id on every cache table that has the column.

    Cache reads filter on repo_id, so a missing index means a sequential scan.
    Tables are discovered at runtime, so new tables are covered
    automatically, and invalid indexes from interrupted builds are recreated.
    cache_bookkeeping gets a (cache_func, repo_id) index instead.
    """
    conn = _connect_with_retry(cache_cx_string)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT columns.table_name
                FROM information_schema.columns AS columns
                JOIN information_schema.tables AS tables
                  ON tables.table_catalog = columns.table_catalog
                 AND tables.table_schema = columns.table_schema
                 AND tables.table_name = columns.table_name
                WHERE columns.table_schema = 'public'
                  AND columns.column_name = 'repo_id'
                  AND columns.table_name != 'cache_bookkeeping'
                  AND tables.table_type = 'BASE TABLE'
                """
            )
            tables = [row[0] for row in cur.fetchall()]

            indexes = [(f"{table}_repo_id_idx", table, ("repo_id",)) for table in tables] + [
                ("cache_bookkeeping_func_repo_idx", "cache_bookkeeping", ("cache_func", "repo_id"))
            ]
            cur.execute(
                """
                SELECT index_class.relname
                FROM pg_catalog.pg_index AS index_info
                JOIN pg_catalog.pg_class AS index_class ON index_class.oid = index_info.indexrelid
                JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = index_class.relnamespace
                WHERE namespace.nspname = 'public' AND NOT index_info.indisvalid
                """
            )
            invalid_indexes = {row[0] for row in cur.fetchall()}

            for index_name, table, columns in indexes:
                if index_name in invalid_indexes:
                    cur.execute(
                        pg_sql.SQL("DROP INDEX CONCURRENTLY IF EXISTS {}.{}").format(
                            pg_sql.Identifier("public"), pg_sql.Identifier(index_name)
                        )
                    )
                cur.execute(
                    pg_sql.SQL("CREATE INDEX CONCURRENTLY IF NOT EXISTS {} ON {}.{} ({})").format(
                        pg_sql.Identifier(index_name),
                        pg_sql.Identifier("public"),
                        pg_sql.Identifier(table),
                        pg_sql.SQL(", ").join(map(pg_sql.Identifier, columns)),
                    )
                )
    finally:
        conn.close()
    logging.warning(f"db_init: ensured repo_id indexes ({len(tables)} tables)")


def _cache_schema_exists() -> bool:
    """Return whether this database already contains an 8Knot cache schema."""
    conn = _connect_with_retry(cache_cx_string)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_type = 'BASE TABLE'
                      AND table_name != 'alembic_version'
                )
                """
            )
            return cur.fetchone()[0]
    finally:
        conn.close()


def _alembic_config() -> Config:
    """Alembic config for migrations/ next to this file; env.py supplies the database URL."""
    here = os.path.dirname(os.path.abspath(__file__))
    return Config(os.path.join(here, "alembic.ini"))


def _stamp_cache_schema() -> None:
    """Mark a new, empty cache as current before creating its tables."""
    command.stamp(_alembic_config(), "head")
    logging.warning("db_init: stamped fresh cache at alembic head")


def _run_cache_migrations() -> None:
    """Apply pending revisions to an existing cache.

    Upgrade rather than stamp head, which would skip migrations on caches
    that have not yet adopted versioning.
    """
    command.upgrade(_alembic_config(), "head")
    logging.warning("db_init: cache schema upgraded to alembic head")


def _flush_redis_broker() -> None:
    """Clear stale Celery messages and results when the cache is initialized.

    The broker is separate from the Redis instance used for user sessions.
    """
    broker_host = os.getenv("REDIS_SERVICE_HOST", "redis-broker")
    broker_port = _env_int("REDIS_SERVICE_PORT", 6379)
    broker_password = os.getenv("REDIS_PASSWORD", "")

    r = redis.StrictRedis(host=broker_host, port=broker_port, password=broker_password)
    r.flushall()
    logging.warning(f"db_init: FLUSHED redis-broker ({broker_host}:{broker_port})")


def db_init() -> int:
    try:
        # don't need to check return values- errors propogate as exceptions,
        # which will halt init altogether.

        # create the configured cache database if it doesn't already exist.
        _create_application_database()

        schema_exists = _cache_schema_exists()

        # Stamp before creating tables, so a retry after an interrupted
        # bootstrap doesn't replay old migrations over the new tables.
        if not schema_exists:
            _stamp_cache_schema()

        _create_application_tables()

        if schema_exists:
            _run_cache_migrations()

        # Reconcile indexes after migrations so they reflect the final schema.
        _ensure_repo_id_indexes()

        _flush_redis_broker()

        logging.warning("db_init: POSTGRES CACHE SUCCESSFULLY INITIALIZED")

        return 0

    except Exception as e:
        logging.critical(f"INITIALIZATION ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(db_init())
