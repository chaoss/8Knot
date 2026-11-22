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
def prs_query(self, repos):
    """
    (Worker Query)
    Executes SQL query against Augur database for pull request data.

    Args:
    -----
        repo_ids ([str]): repos that SQL query is executed on.

    Returns:
    --------
        dict: Results from SQL query, interpreted from pd.to_dict('records')
    """
    logging.warning(f"{prs_query.__name__} COLLECTION - START")

    if len(repos) == 0:
        return None

    query_string = """
                    SELECT
                        r.repo_id,
                        r.repo_name,
                        pr.pull_request_id,
                        pr.pr_src_number,
                        left(pr.pr_augur_contributor_id::text, 15) as cntrb_id,
                        -- values are timestamp not timestamptz
                        pr.pr_created_at AS created_at,
                        pr.pr_closed_at AS closed_at,
                        pr.pr_merged_at AS merged_at,
                        left(pre.cntrb_id::text, 15) AS merger_cntrb_id
                    FROM repo r
                    JOIN pull_requests pr ON r.repo_id = pr.repo_id
                    LEFT JOIN pull_request_events pre
                        ON pr.pull_request_id = pre.pull_request_id AND pre.action = 'merged'
                    WHERE
                        r.repo_id IN %s
                        and pr.pr_created_at < now()
                        and (pr.pr_closed_at < now() or pr.pr_closed_at IS NULL)
                        and (pr.pr_merged_at < now() or pr.pr_merged_at IS NULL)
                        -- have to accept NULL values because PRs could still be open, or unassigned,
                        -- and still be acceptable.
                    ORDER BY pr.pr_created_at
                    """

    # used for caching
    func_name = prs_query.__name__

    # raises Exception on failure. Returns nothing.
    cf.caching_wrapper(
        func_name=func_name,
        query=query_string,
        repolist=repos,
    )
    """
    Old post-processing steps:

    # change to compatible type and remove all data that has been incorrectly formated
    df["created"] = pd.to_datetime(df["created"], utc=True).dt.date
    df = df[df.created < dt.date.today()]

    # reformat cntrb_id
    df["cntrb_id"] = df["cntrb_id"].astype(str)
    df["cntrb_id"] = df["cntrb_id"].str[:15]

    # sort by the date created
    df = df.sort_values(by="created")
    """

    logging.warning(f"{prs_query.__name__} COLLECTION - END")
