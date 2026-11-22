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
def pr_file_query(self, repos):
    """
    (Worker Query)
    Executes SQL query against Augur database for file pull request data.

    Args:
    -----
        repo_ids ([str]): repos that SQL query is executed on.

    Returns:
    --------
        dict: Results from SQL query, interpreted from pd.to_dict('records')
    """
    logging.warning(f"{pr_file_query.__name__}_DATA_QUERY - START")

    if len(repos) == 0:
        return None

    query_string = """
                    SELECT
                        file_path,
                        pull_request_id AS pull_request,
                        repo_id
                    FROM
                        explorer_pr_files
                    WHERE
                        repo_id IN %s
                """

    func_name = pr_file_query.__name__
    cf.caching_wrapper(func_name=func_name, query=query_string, repolist=repos)

    logging.warning(f"{func_name} COLLECTION - END")
    return 0
