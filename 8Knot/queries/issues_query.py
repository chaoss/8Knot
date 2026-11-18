import logging
from app import celery_app
import cache_manager.cache_facade as cf


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    exponential_backoff=2,
    retry_kwargs={"max_retries": 5},
    retry_jitter=True,
)
def issues_query(self, repos):
    """
    (Worker Query)
    Executes SQL query against Augur database for issue data.

    Args:
    -----
        repo_ids ([str]): repos that SQL query is executed on.

    Returns:
    --------
        dict: Results from SQL query, interpreted from pd.to_dict('records')
    """

    logging.warning(f"{issues_query.__name__} COLLECTION - START")

    if len(repos) == 0:
        return None

    query_string = f"""
                    SELECT
                        r.repo_id,
                        r.repo_name,
                        i.issue_id AS issue,
                        i.gh_issue_number AS issue_number,
                        i.gh_issue_id AS gh_issue,
                        left(i.reporter_id::text, 15) as reporter_id,
                        left(i.cntrb_id::text, 15) as issue_closer,
                        -- timestamps are not timestamptz
                        i.created_at,
                        i.closed_at,
                        STRING_AGG(il.label_text, ', ') AS labels
                    FROM
                        repo r
                        JOIN issues i ON r.repo_id = i.repo_id
                        LEFT JOIN issue_labels il ON i.issue_id = il.issue_id
                    WHERE
                        r.repo_id in %s
                        and i.pull_request_id is null
                        and i.created_at < now()
                        and (i.closed_at < now() or i.closed_at IS NULL)
                        -- have to accept NULL values because issues could still be open, or unassigned,
                        -- and still be acceptable.
                    GROUP BY
                        r.repo_id,
                        r.repo_name,
                        i.issue_id,
                        i.gh_issue_number,
                        i.gh_issue_id,
                        i.reporter_id,
                        i.cntrb_id,
                        i.created_at,
                        i.closed_at
                    ORDER BY i.created_at
                    """

    # used for caching
    func_name = issues_query.__name__

    # raises Exception on failure. Returns nothing.
    cf.caching_wrapper(
        func_name=func_name,
        query=query_string,
        repolist=repos,
    )

    """
    Old post-processing steps:

    df = df[df["pull_request_id"].isnull()]
    df = df.drop(columns="pull_request_id")
    df = df.sort_values(by="created")

    # change to compatible type and remove all data that has been incorrectly formated
    df["created"] = pd.to_datetime(df["created"], utc=True).dt.date
    df = df[df.created < dt.date.today()]

    # reformat reporter_id and issue_closer
    df["reporter_id"] = df["reporter_id"].astype(str)
    df["reporter_id"] = df["reporter_id"].str[:15]

    df["issue_closer"] = df["issue_closer"].astype(str)
    df["issue_closer"] = df["issue_closer"].str[:15]
    """

    logging.warning(f"{issues_query.__name__} COLLECTION - END")
