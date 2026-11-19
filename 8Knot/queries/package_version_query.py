import logging
from typing import List, Optional
import cache_manager.cache_facade as cf
from app import celery_app


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=2,
    retry_kwargs={"max_retries": 5},
    retry_jitter=True,
)
def package_version_query(self, repos: List[int]) -> Optional[dict]:
    """
    Celery Worker Task:
    Executes SQL query against Augur database for package dependency versioning data.

    Args:
        repos (List[int]): Repository IDs

    Returns:
        Optional[dict]: Cached query results
    """

    logging.info(f"{package_version_query.__name__} - START")

    # Validate input
    if not repos:
        logging.info("No repositories provided. Skipping query.")
        return None

    if not isinstance(repos, list):
        raise ValueError("repos must be a list of repository IDs")

    # Convert to tuple for safe SQL IN usage
    repos_tuple = tuple(repos)

    query_string = """
        WITH latest_repo_data AS (
            SELECT DISTINCT ON (repo_id)
                repo_id,
                data_collection_date
            FROM repo_deps_libyear
            WHERE repo_id IN %s
            ORDER BY repo_id, data_collection_date DESC
        )
        SELECT
            rdl.repo_id AS id,
            rdl.name,
            rdl.current_release_date,
            rdl.latest_release_date,
            rdl.libyear,
            CASE
                WHEN rdl.libyear >= 1.0 THEN 'Greater than a year'
                WHEN rdl.libyear > 0.5 THEN '6 months to year'
                WHEN rdl.libyear > 0 THEN 'Less than 6 months'
                WHEN rdl.libyear = 0 THEN 'Up to date'
                ELSE 'Unclear version history'
            END AS dep_age
        FROM repo_deps_libyear rdl
        JOIN latest_repo_data lrd
            ON rdl.repo_id = lrd.repo_id
            AND rdl.data_collection_date = lrd.data_collection_date
        WHERE rdl.libyear >= 0
    """

    func_name = package_version_query.__name__

    cf.caching_wrapper(
        func_name=func_name,
        query=query_string,
        repolist=repos_tuple,
        n_repolist_uses=1,
    )

    logging.info(f"{package_version_query.__name__} - END")