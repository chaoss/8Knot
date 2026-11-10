"""
Interface to the PostgreSQL cache. Source results stream through SQLAlchemy;
bulk cache writes use psycopg2.
"""

import logging
import re
from typing import Optional
import psycopg2 as pg
from psycopg2.extras import execute_values
from psycopg2 import sql as pg_sql
import pandas as pd
from sqlalchemy.exc import DBAPIError
from db_manager.collectoss_manager import CollectOSSManager
from models import SearchItem, clean_repo_name

# requires relative import syntax "import .cx_common" because
# other files importing cache_facade need to know how to resolve
# .cx_common- interpreter is invoked at a higher level, so relative
# import required.
from .cx_common import cache_cx_string

# The engine is opened lazily in the worker process and reused between tasks.
collectoss = CollectOSSManager(worker_query=True)


class SearchOptionsEmpty(Exception):
    """search_options has no rows: the startup sync failed or cache crash recovery truncated it."""


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
            with pg.connect(cache_cx_string) as cache_conn:
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

        # don't need to commit on primary db
        logging.warning(f"{target_table} -- CQR SUCCESS")


def get_uncached(func_name: str, repolist: list[int]) -> list[int]:  # or None
    """
    Checks bookkeeping data to find, for a given querying function, which
    repos' data are noted as present in cache vs. those that arent.

    Returns a list of repos that AREN'T resident in cache.
    """
    with pg.connect(cache_cx_string) as cache_conn:
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
            already_cached: set[int] = set([v[0] for v in already_cached])

            # repos that are already cached will be removed from repolist set,
            # leaving uncached remaining.
            not_cached: list[int] = list(set(repolist) - already_cached)

            return not_cached


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
    try:
        # STEP 1: Which repos need to be queried for?
        #           some might already be in cache.
        uncached_repos: list[int] | None = get_uncached(func_name=func_name, repolist=repolist)
        if not uncached_repos:
            logging.warning(f"{func_name} COLLECTION - ALL REQUESTED REPOS IN CACHE")
            return 0
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


def sync_search_options(options: list[dict[str, str]]) -> None:
    """
    Makes postgres-cache's search_options table match the searchbar options from CollectOSS:
    changed rows are upserted and rows no longer in CollectOSS are deleted.

    Args:
        options: [{"label": str, "value": str}, ...] from the CollectOSS manager's get_multiselect_options().
    """
    if not options:
        return

    # keyed by value: ON CONFLICT can't update the same row twice in one statement
    rows = {}
    for opt in options:
        item_type = SearchItem.from_id(opt["value"]).value
        rows[opt["value"]] = (opt["value"], opt["label"], clean_repo_name(opt["label"])[0], item_type)

    with pg.connect(cache_cx_string) as cache_conn:
        with cache_conn.cursor() as cache_cur:
            # every process that imports app.py syncs at startup; run them one at a time
            cache_cur.execute("SELECT pg_advisory_xact_lock(hashtext('8knot_search_options_sync'))")
            execute_values(
                cur=cache_cur,
                sql="""
                INSERT INTO search_options (value, label, search_text, item_type)
                VALUES %s
                ON CONFLICT (value) DO UPDATE SET
                    label = EXCLUDED.label,
                    search_text = EXCLUDED.search_text,
                    item_type = EXCLUDED.item_type
                -- skip unchanged rows so restarts don't rewrite (and bloat) the whole table
                WHERE (search_options.label, search_options.search_text, search_options.item_type)
                    IS DISTINCT FROM (EXCLUDED.label, EXCLUDED.search_text, EXCLUDED.item_type)
                """,
                argslist=list(rows.values()),
                page_size=2000,
            )
            # anti-join rather than "value <> ALL(array)", which PG < 15 can't hash: 11 s vs 17 ms at 43k rows
            cache_cur.execute(
                """
                DELETE FROM search_options s
                WHERE NOT EXISTS (SELECT 1 FROM unnest(%s::text[]) AS keep(value) WHERE keep.value = s.value)
                """,
                (list(rows),),
            )
            deleted = cache_cur.rowcount
        cache_conn.commit()
    logging.warning(f"search_options - SYNCED {len(rows)} OPTIONS, DELETED {deleted} STALE")


def search_options_query(
    query_str: str,
    item_type: Optional[str] = None,
) -> list[dict[str, str]]:
    """
    Searches search_options in postgres-cache by word prefix (full-text search on search_tsv) and,
    for queries of 3+ characters, by substring and trigram similarity (pg_trgm) for typo tolerance.

    Args:
        query_str: User's search query (without repo:/org: prefix). A pasted repo URL is reduced
            to owner/repo, matching how search_text is built.
        item_type: Optional filter ('repo' or 'org').

    Returns:
        Up to 100 {'label': str, 'value': str} dicts, best matches first; orgs come before repos
        among equally good matches.

    Raises:
        SearchOptionsEmpty: If search_options has no rows, so the caller can re-sync it.
    """
    cleaned_query = clean_repo_name(query_str.strip())[0]
    if not cleaned_query:
        return []

    tokens = re.findall(r"[^\W_]+", cleaned_query.lower())
    escaped_like = re.sub(r"([%_\\])", r"\\\1", cleaned_query)
    params = {
        "raw_query": cleaned_query,
        "tsquery": " & ".join(f"{token}:*" for token in tokens),
        # trigrams need 3+ characters, so shorter queries only match word prefixes
        "long_query": len(cleaned_query) > 2,
        "repo_name_pattern": f"%/{escaped_like}",
        "prefix_pattern": f"{escaped_like}%",
        "contains_pattern": f"%{escaped_like}%",
        "item_type": item_type,
    }

    with pg.connect(cache_cx_string) as cache_conn:
        with cache_conn.cursor() as cache_cur:
            cache_cur.execute("SET LOCAL pg_trgm.word_similarity_threshold = 0.35")
            cache_cur.execute(
                """
                SELECT value, label
                FROM search_options
                WHERE (
                    (%(tsquery)s != '' AND search_tsv @@ to_tsquery('simple', %(tsquery)s))
                    OR (
                        %(long_query)s
                        AND (search_text ILIKE %(contains_pattern)s OR %(raw_query)s <%% search_text)
                    )
                )
                AND (%(item_type)s IS NULL OR item_type = %(item_type)s)
                ORDER BY
                    CASE
                        WHEN lower(search_text) = lower(%(raw_query)s) THEN 0
                        -- exact repo name ("owner/<query>"), so it isn't outranked by owner-prefix matches
                        WHEN search_text ILIKE %(repo_name_pattern)s THEN 1
                        WHEN search_text ILIKE %(prefix_pattern)s THEN 2
                        WHEN %(tsquery)s != '' AND search_tsv @@ to_tsquery('simple', %(tsquery)s) THEN 3
                        WHEN search_text ILIKE %(contains_pattern)s THEN 4
                        ELSE 5
                    END,
                    CASE WHEN item_type = 'org' THEN 0 ELSE 1 END,
                    CASE
                        WHEN %(tsquery)s != '' THEN ts_rank(search_tsv, to_tsquery('simple', %(tsquery)s))
                        ELSE 0.0
                    END DESC,
                    word_similarity(%(raw_query)s, search_text) DESC,
                    length(search_text) ASC,
                    search_text ASC
                LIMIT 100
                """,
                params,
            )
            rows = cache_cur.fetchall()
            if not rows:
                # tell "no match" apart from an empty table (failed startup sync, cache crash recovery)
                cache_cur.execute("SELECT EXISTS (SELECT 1 FROM search_options)")
                if not cache_cur.fetchone()[0]:
                    raise SearchOptionsEmpty()
            return [{"label": row[1], "value": row[0]} for row in rows]
