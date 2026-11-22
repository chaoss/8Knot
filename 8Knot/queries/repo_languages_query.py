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
def repo_languages_query(self, repos):
    """
    (Worker Query)
    Executes SQL query against Augur database for file language data.

    Explorer_repo_languages is a materialized view on the database for quicker run time and
    may not be in your augur database. The SQL query content can be found
    in docs/materialized_views/explorer_repo_languages.sql

    Args:
    -----
        repos ([int]): repos that SQL query is executed on.

    Returns:
    --------
        dict: Results from SQL query, interpreted from pd.to_dict('records')

    """
    logging.warning(f"{repo_languages_query.__name__} COLLECTION - START")

    if len(repos) == 0:
        return None

    query_string = """
                    SELECT
                        repo_id as id,
                        programming_language,
                        code_lines,
                        files
                    FROM explorer_repo_languages
                    WHERE repo_id in %s
                """

    func_name = repo_languages_query.__name__

    # raises Exception on failure. Returns nothing.
    cf.caching_wrapper(
        func_name=func_name,
        query=query_string,
        repolist=repos,
    )

    logging.warning(f"{repo_languages_query.__name__} COLLECTION - END")
