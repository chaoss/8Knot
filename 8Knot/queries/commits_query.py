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
def commits_query(self, repos):
    """
    (Worker Query)
    Executes SQL query against Augur database for commit data.

    Args:
    -----
        repo_ids (list[int]): repos that SQL query is executed on.

    Returns:
    --------
        dict: Results from SQL query, interpreted from pd.to_dict('records')
    """
    logging.warning(f"{commits_query.__name__} COLLECTION - START")

    if len(repos) == 0:
        return None

    # commenting-out unused query components. only need the repo_id and the
    # authorship date for our current queries. remove the '--' to re-add
    # the now-removed values.
    query_string = """
                    SELECT
                        distinct
                        r.repo_id as repo_id,
                        c.cmt_commit_hash AS commit_hash,
                        c.cmt_author_email AS author_email,
                        c.cmt_author_date AS author_date,
                        -- all timestamptz's are coerced to utc from their origin timezones.
                        timezone('utc', c.cmt_author_timestamp) AS author_timestamp,
                        timezone('utc', c.cmt_committer_timestamp) AS committer_timestamp

                    FROM
                        repo r
                    JOIN commits c
                        ON r.repo_id = c.repo_id
                    WHERE
                        c.repo_id in %s
                        and timezone('utc', c.cmt_author_timestamp) < now()
                        and timezone('utc', c.cmt_committer_timestamp) < now()
                        -- Above queries are always non-null so we don't have to check them.
                    """

    # used for caching
    func_name = commits_query.__name__

    # raises Exception on failure. Returns nothing.
    cf.caching_wrapper(
        func_name=func_name,
        query=query_string,
        repolist=repos,
    )

    """
    Original post-processing steps

    # change to compatible type and remove all data that has been incorrectly formated
    df["author_timestamp"] = pd.to_datetime(df["author_timestamp"], utc=True).dt.date
    df = df[df.author_timestamp < dt.date.today()]
    """

    logging.warning(f"{commits_query.__name__} COLLECTION - END")
    return 0
