import logging
import pandas as pd
from db_manager.collectoss_manager import CollectOSSManager
from app import celery_app
import cache_manager.cache_facade as cf


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    exponential_backoff=2,
    retry_kwargs={"max_retries": 5},
    retry_jitter=True,
)
def repo_files_query(self, repos):
    """
    (Worker Query)
    Executes SQL query against Augur database to get the repo file data.

    Args:
    -----
        repo_ids ([str]): repos that SQL query is executed on.

    Returns:
    --------
        dict: Results from SQL query, interpreted from pd.to_dict('records')
    """
    logging.warning(f"{repo_files_query.__name__}_DATA_QUERY - START")

    if len(repos) == 0:
        return None

    # Use pre-computed materialized view for faster performance
    query_string = """
                    SELECT
                        id AS repo_id,
                        repo_name,
                        repo_path,
                        rl_analysis_date,
                        file_path,
                        file_name
                    FROM
                        explorer_repo_files
                    WHERE
                        id IN %s
                        AND repo_name IS NOT NULL
                        AND repo_path IS NOT NULL
                """

    func_name = repo_files_query.__name__
    cf.caching_wrapper(func_name=func_name, query=query_string, repolist=repos)

    logging.warning(f"{func_name} COLLECTION - END")
    return 0
