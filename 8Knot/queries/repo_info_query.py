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
def repo_info_query(self, repos):
    """
    (Worker Query)
    Executes SQL query against Augur database for package dependency versioning data.

    Args:
    -----
        repos ([int]): repos that SQL query is executed on.

    Returns:
    --------
        dict: Results from SQL query, interpreted from pd.to_dict('records')

    """
    logging.warning(f"{repo_info_query.__name__} COLLECTION - START")

    if len(repos) == 0:
        return None

    query_string = """
                SELECT DISTINCT
                    repo_id AS id,
                    issues_enabled,
                    fork_count,
                    watchers_count,
                    license,
                    stars_count,
                    code_of_conduct_file,
                    security_issue_file,
                    security_audit_file,
                    data_collection_date
                FROM
                    repo_info ri
                WHERE
                    repo_id IN %s AND
                    (repo_id, data_collection_date) IN (
                        SELECT DISTINCT ON (repo_id)
                            repo_id, data_collection_date
                        FROM repo_info
                        WHERE
                            repo_id IN %s
                        ORDER BY repo_id, data_collection_date DESC
                        )
                """

    func_name = repo_info_query.__name__

    # raises Exception on failure. Returns nothing.
    cf.caching_wrapper(func_name=func_name, query=query_string, repolist=repos, n_repolist_uses=2)

    logging.warning(f"{repo_info_query.__name__} COLLECTION - END")
