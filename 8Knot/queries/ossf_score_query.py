import logging
import cache_manager.cache_facade as cf
from _celery import celery_app


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    exponential_backoff=2,
    retry_kwargs={"max_retries": 5},
    retry_jitter=True,
)
def ossf_score_query(self, repos):
    """
    (Worker Query)
    Executes SQL query against Augur database for repo ossf scorecard information.

    Args:
    -----
        repos ([int]): repos that SQL query is executed on.

    Returns:
    --------
        dict: Results from SQL query, interpreted from pd.to_dict('records')

    """
    logging.warning(f"{ossf_score_query.__name__} COLLECTION - START")

    if len(repos) == 0:
        return None

    query_string = """
                SELECT
                    rds.repo_id,
                    rds.name,
                    rds.score,
                    rds.data_collection_date
                FROM
                    repo_deps_scorecard rds
                JOIN (
                    SELECT repo_id, MAX(data_collection_date) AS max_date
                    FROM repo_deps_scorecard
                    WHERE repo_id IN %s
                    GROUP BY repo_id
                ) latest
                ON latest.repo_id = rds.repo_id
                AND latest.max_date = rds.data_collection_date
                WHERE rds.repo_id IN %s
                """

    func_name = ossf_score_query.__name__

    # raises Exception on failure. Returns nothing.
    cf.caching_wrapper(
        func_name=func_name,
        query=query_string,
        repolist=repos,
        n_repolist_uses=2,
    )

    logging.warning(f"{ossf_score_query.__name__} COLLECTION - END")
