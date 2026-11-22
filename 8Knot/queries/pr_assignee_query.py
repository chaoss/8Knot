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
def pr_assignee_query(self, repos):
    """
    (Worker Query)
    Executes SQL query against Augur database for contributor data.

    Explorer_pr_assignments is a materialized view on the database for quicker run time and
    may not be in your augur database. The SQL query content can be found
    in docs/materialized_views/explorer_pr_assignments.sql

    Args:
    -----
        repo_ids ([str]): repos that SQL query is executed on.
    Returns:
    --------
        dict: Results from SQL query, interpreted from pd.to_dict('records')
    """
    logging.warning(f"{pr_assignee_query.__name__} COLLECTION - START")

    if len(repos) == 0:
        return None

    query_string = f"""
                    SELECT
                        pa.pull_request_id,
                        pa.id,
                        -- below are timestamp not timestamptz
                        pa.created,
                        pa.closed,
                        pa.assign_date,
                        pa.assignment_action,
                        left(pa.assignee::text, 15) as assignee
                    FROM
                        explorer_pr_assignments pa
                    WHERE
                        pa.id in %s
                        and pa.created < now()
                        and (pa.closed < now() or pa.closed IS NULL)
                        and (pa.assign_date < now() or pa.assign_date IS NULL)
                        -- have to accept NULL values because PRs could still be open, or unassigned,
                        -- and still be acceptable.
                """

    # used for caching
    func_name = pr_assignee_query.__name__

    # raises Exception on failure. Returns nothing.
    cf.caching_wrapper(
        func_name=func_name,
        query=query_string,
        repolist=repos,
    )

    """
    Old post-processing steps:

    # id as string and slice to remove excess 0s
    df["assignee"] = df["assignee"].astype(str)
    df["assignee"] = df["assignee"].str[:15]

    # change to compatible type and remove all data that has been incorrectly formated
    df["created"] = pd.to_datetime(df["created"], utc=True).dt.date
    df = df[df.created < dt.date.today()]
    """

    logging.warning(f"{pr_assignee_query.__name__} COLLECTION - END")
