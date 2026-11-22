"""
Interface to the PostgreSQL cache. Source results stream through SQLAlchemy;
bulk cache writes use psycopg2.
"""

import logging
from contextlib import closing
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
    cache_conn,
    server_pagination=2000,
    client_pagination=2000,
) -> None:
    """Stream results and bookkeeping into the caller's locked cache transaction.
    Retrieves results from db with paginations {server_pagination} and {client_pagination}.

    Args:
        query (str): _description_
        vars (tuple(tuple)): _description_
        target_table (str): _description_
        bookkeeping_data (tuple(dict)): _description_
        cache_conn: Cache connection; caller owns commit/rollback and collection lock.
        server_pagination (int, optional): _description_. Defaults to 2000.
        client_pagination (int, optional): _description_. Defaults to 2000.
    """
    logging.warning(f"{target_table} -- CQR CACHE_QUERY_RESULTS BEGIN")
    with collectoss.get_engine().connect() as collectoss_conn:
        logging.warning(f"{target_table} -- CQR EXECUTING QUERY")
        # A server-side cursor keeps large results out of worker memory.
        with collectoss_conn.execution_options(yield_per=server_pagination).exec_driver_sql(query, vars) as result:
            logging.warning(f"{target_table} -- CQR STARTING TRANSACTION")
            composed_query = (
                pg_sql.SQL("INSERT INTO {} VALUES %s").format(pg_sql.Identifier(target_table)).as_string(cache_conn)
            )

            logging.warning(f"{target_table} -- CQR FETCHING AND STORING ROWS")
            while rows := result.fetchmany(client_pagination):
                with cache_conn.cursor() as cache_cur:
                    execute_values(
                        cur=cache_cur,
                        sql=composed_query,
                        argslist=[tuple(row) for row in rows],
                        page_size=client_pagination,
                    )

            # Empty successful results are cached too; failed streams never reach this.
            logging.warning(f"{target_table} -- CQR UPDATING BOOKKEEPING")
            with cache_conn.cursor() as cache_cur:
                execute_values(
                    cur=cache_cur,
                    sql="INSERT INTO cache_bookkeeping (cache_func, repo_id) VALUES %s",
                    template="(%(cache_func)s, %(repo_id)s)",
                    argslist=bookkeeping_data,
                )


def _get_uncached(cache_conn, func_name, repolist):
    """Read completed entries on an existing transaction (not a collection claim)."""
    with cache_conn.cursor() as cache_cur:
        cache_cur.execute(
            "SELECT repo_id FROM cache_bookkeeping WHERE cache_func = %s AND repo_id = ANY(%s)",
            (func_name, list(repolist)),
        )
        already_cached = {row[0] for row in cache_cur.fetchall()}
    return sorted(set(repolist) - already_cached)


def get_uncached(func_name: str, repolist: list[int]) -> list[int]:
    """
    Checks bookkeeping data to find, for a given querying function, which
    repos' data are noted as present in cache vs. those that arent.

    Returns a list of repos that AREN'T resident in cache.
    """
    if not repolist:
        return []
    with closing(pg.connect(cache_cx_string)) as cache_conn, cache_conn:
        return _get_uncached(cache_conn, func_name, repolist)


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
        return 0
    try:
        with closing(pg.connect(cache_cx_string)) as cache_conn, cache_conn:
            # Claim (query, repo) keys in canonical order so overlapping tasks
            # cannot deadlock. Keep claims through recheck + collection + commit.
            repo_claims = sorted(set(repolist))
            with cache_conn.cursor() as cur:
                cur.execute("SET LOCAL lock_timeout = '5s'")
                for repo_id in repo_claims:
                    cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s), %s)", (func_name, repo_id))
            uncached_repos = _get_uncached(cache_conn, func_name, repolist)
            if not uncached_repos:
                logging.warning(f"{func_name} COLLECTION - ALL REQUESTED REPOS IN CACHE")
                return 0
            logging.warning(f"{func_name} COLLECTION - CACHING {len(uncached_repos)} NEW REPOS")
            cache_query_results(
                query=query,
                vars=tuple(tuple(uncached_repos) for _ in range(n_repolist_uses)),
                target_table=func_name,
                bookkeeping_data=tuple({"cache_func": func_name, "repo_id": r} for r in uncached_repos),
                cache_conn=cache_conn,
            )
            logging.warning(f"{func_name} -- CQR COMMITTING TRANSACTION")
        logging.warning(f"{func_name} -- CQR SUCCESS")
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

    # GET ALL DATA FROM POSTGRES CACHE
    df = None
    with pg.connect(cache_cx_string) as cache_conn:
        with cache_conn.cursor() as cache_cur:
            cache_cur.execute(
                """
                SELECT *
                FROM {tablename} t
                WHERE t.repo_id IN %s;
                """.format(
                    tablename=tablename
                ),
                (tuple(repolist),),
            )

            logging.warning(f"{tablename} - LOADING DATA FROM CACHE")
            df = pd.DataFrame(
                cache_cur.fetchall(),
                # get df column names from the database columns
                columns=[desc[0] for desc in cache_cur.description],
            )
            logging.warning(f"{tablename} - DATA LOADED - {df.shape} rows,cols")
            return df
