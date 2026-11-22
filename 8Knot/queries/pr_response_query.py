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
def pr_response_query(self, repos):
    """
    (Worker Query)
    Executes SQL query against Augur database for contributor data.

    This query gets the messages that are in response to a pr if any exists,
    if not the msg_timestamp is null. It takes in the data
    of the comments (messages) on prs and pr reviews for each pr if it exists.

    explorer_pr_response is a materialized view on the database for quicker run time and
    may not be in your augur database. The SQL query content can be found
    in docs/materialized_views/explorer_pr_response.sql

    Args:
    -----
        repo_ids ([str]): repos that SQL query is executed on.

    Returns:
    --------
        dict: Results from SQL query, interpreted from pd.to_dict('records')
    """
    logging.warning(f"{pr_response_query.__name__}_DATA_QUERY - START")

    if len(repos) == 0:
        return None

    query_string = """
                    SELECT
                        *
                    FROM
                        explorer_pr_response epr
                    WHERE
                        epr.ID in %s
                """

    func_name = pr_response_query.__name__
    cf.caching_wrapper(func_name=func_name, query=query_string, repolist=repos)

    logging.warning(f"{func_name} COLLECTION - END")
    return 0
