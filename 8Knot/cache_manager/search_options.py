"""
Searchbar index in postgres-cache: the search_options table (created in db_init.py)
is synced from CollectOSS at startup and queried on every searchbar keystroke.
"""

import logging
import re
from typing import Optional
import psycopg2 as pg
from psycopg2.extras import execute_values
from models import SearchItem, clean_repo_name

# relative import, as in cache_facade.py
from .cx_common import cache_cx_string


class SearchOptionsEmpty(Exception):
    """search_options has no rows: the startup sync failed or cache crash recovery truncated it."""


def sync(options: list[dict[str, str]]) -> None:
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


def query(
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
