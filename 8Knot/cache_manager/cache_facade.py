"""
Interface to the PostgreSQL cache. Source results stream through SQLAlchemy;
bulk cache writes use psycopg2.
"""

import logging
import time
import psycopg2 as pg
from psycopg2.extras import execute_values
from psycopg2 import sql as pg_sql
import pandas as pd
from sqlalchemy.exc import DBAPIError
from db_manager.collectoss_manager import CollectOSSManager

# requires relative import syntax "import .cx_common" because
# other files importing cache_facade need to know how to resolve
# .cx_common- interpreter is invoked at a higher level, so relative
# import required.
from .cx_common import cache_cx_string

# The engine is opened lazily in the worker process and reused between tasks.
collectoss = CollectOSSManager(worker_query=True)


def cache_query_results(
    query: str,
    vars: tuple[tuple],
    target_table: str,
    bookkeeping_data: tuple[dict],
    server_pagination=2000,
    client_pagination=2000,
) -> None:
    """Runs {query} against CollectOSS with variables {vars}.
    Retrieves results from db with paginations {server_pagination} and {client_pagination}.

    Args:
        query (str): _description_
        vars (tuple(tuple)): _description_
        target_table (str): _description_
        bookkeeping_data (tuple(dict)): _description_
        server_pagination (int, optional): _description_. Defaults to 2000.
        client_pagination (int, optional): _description_. Defaults to 2000.
    """
    logging.warning(f"{target_table} -- CQR CACHE_QUERY_RESULTS BEGIN")
    with collectoss.get_engine().connect() as collectoss_conn:
        logging.warning(f"{target_table} -- CQR EXECUTING QUERY")
        # A server-side cursor keeps large results out of worker memory.
        with collectoss_conn.execution_options(yield_per=server_pagination).exec_driver_sql(query, vars) as result:
            logging.warning(f"{target_table} -- CQR STARTING TRANSACTION")
            # connect to cache
            cache_conn = pg.connect(cache_cx_string)
            try:
                logging.warning(f"{target_table} -- CQR COMPOSING SQL")
                # compose SQL w/ table name
                # ref: https://www.psycopg.org/docs/sql.html
                composed_query = pg_sql.SQL(
                    "INSERT INTO {tbl_name} VALUES %s ON CONFLICT DO NOTHING".format(tbl_name=target_table)
                ).as_string(cache_conn)

                # iterate through pages of rows from server.
                logging.warning(f"{target_table} -- CQR FETCHING AND STORING ROWS")
                while rows := result.fetchmany(client_pagination):
                    # write available rows to cache.
                    with cache_conn.cursor() as cache_cur:
                        execute_values(
                            cur=cache_cur,
                            sql=composed_query,
                            argslist=[tuple(row) for row in rows],
                            page_size=client_pagination,
                        )

                # after all data has successfully been written to cache from the primary db,
                # insert record of existence for each (cache_func, repo_id) pair.
                logging.warning(f"{target_table} -- CQR UPDATING BOOKKEEPING")
                with cache_conn.cursor() as cache_cur:
                    execute_values(
                        cur=cache_cur,
                        sql="""
                        INSERT INTO cache_bookkeeping (cache_func, repo_id)
                        VALUES %s
                        """,
                        template="(%(cache_func)s, %(repo_id)s)",
                        argslist=bookkeeping_data,
                    )

                logging.warning(f"{target_table} -- CQR COMMITTING TRANSACTION")
                cache_conn.commit()
            finally:
                cache_conn.close()

        # don't need to commit on primary db
        logging.warning(f"{target_table} -- CQR SUCCESS")


def get_uncached(func_name: str, repolist: list[int]) -> list[int]:  # or None
    """
    Checks bookkeeping data to find, for a given querying function, which
    repos' data are noted as present in cache vs. those that arent.

    Returns a list of repos that AREN'T resident in cache.
    """
    if not repolist:
        return []

    cache_conn = pg.connect(cache_cx_string)
    try:
        with cache_conn.cursor() as cache_cur:
            composed_query = pg_sql.SQL(
                """
                SELECT cb.repo_id
                FROM cache_bookkeeping cb
                WHERE cb.cache_func = '{cache_func_name}' AND cb.repo_id in %s
                """.format(
                    cache_func_name=func_name
                )
            ).as_string(cache_conn)

            # exec query
            cache_cur.execute(query=composed_query, vars=(tuple(repolist),))

            # get list of cached repos
            already_cached: list[tuple] = cache_cur.fetchall()

            # process list of single-value tuples to get list of values.
            # looks like: [(val1,), (val2,), ...]
            already_cached_set: set[int] = set([v[0] for v in already_cached])

            # repos that are already cached will be removed from repolist set,
            # leaving uncached remaining.
            not_cached: list[int] = list(set(repolist) - already_cached_set)

            return not_cached
    finally:
        cache_conn.close()


def wait_for_cache(
    func_name: str,
    repolist: list[int],
    timeout: int = 60,
    caller: str = "",
) -> None:
    """Wait for data to appear in cache with bounded polling and backoff.

    Replaces the per-visualization `while not_cached := get_uncached(...): time.sleep(0.5)`
    polling loops. Uses progressive backoff (0.5s -> 1.0s -> 2.0s capped at 5.0s) to reduce
    load on postgres-cache while queries are running.

    Args:
        func_name: name of the query function (used for bookkeeping lookup).
        repolist: repo IDs expected in cache.
        timeout: max seconds to wait before raising TimeoutError.
        caller: optional label for log messages.
    """
    if not repolist:
        return

    label = caller or func_name
    delay = 0.5
    max_delay = 5.0
    deadline = time.monotonic() + timeout

    while not_cached := get_uncached(func_name=func_name, repolist=repolist):
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"{label}: timed out after {timeout}s waiting for {len(not_cached)} repos in {func_name}"
            )
        logging.warning(f"{label} - WAITING ON {len(not_cached)} REPOS FOR {func_name}")
        time.sleep(delay)
        delay = min(delay * 2, max_delay)


def caching_wrapper(func_name: str, query: str, repolist: list[int], n_repolist_uses=1) -> None:
    """Combines steps of (1) identifying which repos aren't already cached and
    (2) querying + caching repos those repos.

    Args:
        func_name (str): literal name of querying function for bookkeeping
        query (str): sql query as a string
        repolist (list[int]): list of repos requested by user.
        n_repolist_uses (int): if the repolist is used more than once in the query, simply inject it again.
                                TODO: remove this hack and parameterize queries by name

    Raises:
        Exception: If a step fails, will print exception and re-raise.

    Returns:
        _type_: None
    """
    if not repolist:
        logging.warning(f"{func_name} COLLECTION - NO REPOS SPECIFIED")
        return

    try:
        # STEP 1: Which repos need to be queried for?
        #           some might already be in cache.
        uncached_repos: list[int] | None = get_uncached(func_name=func_name, repolist=repolist)
        if not uncached_repos:
            logging.warning(f"{func_name} COLLECTION - ALL REQUESTED REPOS IN CACHE")
            return
        else:
            logging.warning(f"{func_name} COLLECTION - CACHING {len(uncached_repos)} NEW REPOS")

            # inject the repolist multiple times because the SQL uses it more
            # than once and the wildcard %s are ordered.
            uncached_repos: tuple[tuple] = tuple([tuple(uncached_repos) for _ in range(n_repolist_uses)])

        # STEP 2: Query for those repos
        logging.warning(f"{func_name} COLLECTION - EXECUTING CACHING QUERY")
        cache_query_results(
            query=query,
            vars=uncached_repos,
            target_table=func_name,
            bookkeeping_data=tuple({"cache_func": func_name, "repo_id": r} for r in repolist),
        )
    except Exception as error:
        logging.exception(f"{func_name}_POSTGRES ERROR")

        # SQLAlchemy wraps driver errors. Preserve the cancellation type so
        # Celery's dont_autoretry_for still prevents repeated timed-out queries.
        if isinstance(error, DBAPIError) and isinstance(error.orig, pg.errors.QueryCanceled):
            raise error.orig from error
        raise


def retrieve_from_cache(
    tablename: str,
    repolist: list[int],
) -> pd.DataFrame:
    """
    For a given table in cache, get all results
    that having a matching repo_id.

    Results are retrieved by a DataFrame, so column names
    may need to be overridden by calling function.
    """
    if not repolist:
        return pd.DataFrame()

    # GET ALL DATA FROM POSTGRES CACHE
    df = None
    cache_conn = pg.connect(cache_cx_string)
    try:
        with cache_conn.cursor() as cache_cur:
            composed_query = pg_sql.SQL(
                """
                SELECT *
                FROM {table} t
                WHERE t.repo_id IN %s;
                """
            ).format(table=pg_sql.Identifier(tablename))

            cache_cur.execute(composed_query, (tuple(repolist),))

            logging.warning(f"{tablename} - LOADING DATA FROM CACHE")
            rows = cache_cur.fetchall()
            columns = [desc[0] for desc in cache_cur.description] if cache_cur.description else []
            df = pd.DataFrame(rows, columns=columns)
            logging.warning(f"{tablename} - DATA LOADED - {df.shape} rows,cols")
            return df
    finally:
        cache_conn.close()
