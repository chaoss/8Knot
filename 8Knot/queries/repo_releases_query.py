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
def repo_releases_query(self, repos):
    """
    (Worker Query)
    Executes SQL query against Augur database for repo release information.

    Args:
    -----
        repos ([int]): repos that SQL query is executed on.

    Returns:
    --------
        dict: Results from SQL query, interpreted from pd.to_dict('records')

    """
    logging.warning(f"{repo_releases_query.__name__} COLLECTION - START")

    if len(repos) == 0:
        return None

    query_string = """
                SELECT
                    repo_id AS id,
                    release_name,
                    release_created_at,
                    release_published_at,
                    release_updated_at
                FROM
                    releases r
                WHERE
                    repo_id IN %s AND
                    release_published_at IS NOT NULL
                ORDER BY release_published_at DESC
                """

    func_name = repo_releases_query.__name__

    # raises Exception on failure. Returns nothing.
    cf.caching_wrapper(
        func_name=func_name,
        query=query_string,
        repolist=repos,
    )

    logging.warning(f"{repo_releases_query.__name__} COLLECTION - END")
