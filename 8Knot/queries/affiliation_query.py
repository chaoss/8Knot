import logging
from _celery import celery_app
import cache_manager.cache_facade as cf


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    exponential_backoff=2,
    retry_kwargs={"max_retries": 5},
    retry_jitter=True,
)
def affiliation_query(self, repos):
    """
    (Worker Query)
    Executes SQL query against Augur database for organization affiliation data.

    Explorer_contributor_actions is a materialized view on the database for quicker run time and
    may not be in your augur database. The SQL query content can be found
    in docs/explorer_contributor_actions.sql

    Args:
    -----
        repo_ids ([str]): repos that SQL query is executed on.

    Returns:
    --------
        dict: Results from SQL query, interpreted from pd.to_dict('records')

    """
    logging.warning(f"{affiliation_query.__name__} COLLECTION - START")

    if len(repos) == 0:
        return None

    query_string = f"""
                    WITH contributor_emails AS (
                        -- pre-aggregate one email list per contributor so the main query
                        -- avoids the alias JOIN explosion (O(N*A) -> O(N)).
                        SELECT
                            con.cntrb_id,
                            con.cntrb_company,
                            COALESCE(
                                array_to_string(
                                    array_agg(DISTINCT e) FILTER (WHERE e IS NOT NULL AND e != ''),
                                    ' , '
                                ),
                                ''
                            ) AS email_list
                        FROM contributors con
                        JOIN contributors_aliases ca ON con.cntrb_id = ca.cntrb_id,
                        LATERAL unnest(ARRAY[ca.alias_email, con.cntrb_email, con.cntrb_canonical]) AS e
                        GROUP BY con.cntrb_id, con.cntrb_company
                    )
                    SELECT DISTINCT
                        left(c.cntrb_id::text, 15) AS cntrb_id,
                        timezone('utc', c.created_at) AS created_at,
                        c.repo_id,
                        c.login,
                        c.action,
                        ce.cntrb_company,
                        ce.email_list
                    FROM explorer_contributor_actions c
                    JOIN contributor_emails ce ON c.cntrb_id = ce.cntrb_id
                    WHERE
                        c.repo_id IN %s
                        AND timezone('utc', c.created_at) < now()
                    ORDER BY created_at
                    """

    # used for caching
    func_name = affiliation_query.__name__

    # raises Exception on failure. Returns nothing.
    cf.caching_wrapper(
        func_name=func_name,
        query=query_string,
        repolist=repos,
    )
    """
    Old post-processing steps:

    # reformat cntrb_id
    df["cntrb_id"] = df["cntrb_id"].astype(str)
    df["cntrb_id"] = df["cntrb_id"].str[:15]

    df = df.sort_values(by="created")

    # change to compatible type and remove all data that has been incorrectly formatted
    df["created"] = pd.to_datetime(df["created"], utc=True).dt.date
    df = df[df.created < dt.date.today()]

    """
    logging.warning(f"{affiliation_query.__name__} COLLECTION - END")
