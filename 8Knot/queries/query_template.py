import logging
from _celery import celery_app
import cache_manager.cache_facade as cf

"""
TODO:
(1) Rename the query function to something informative. Replace other instances of "NAME_query" with your
    chosen name. ctrl-f is a good way to do this for every occurence in the file!
(2) Paste SQL query for Augur db into the query_string variable. Use the psycopg2 '%s' wildcard in the string
    where you intend to use the repos list. The '%s' will be replaced with a literal representation of the 'repos' variable.
    NOTE: if you have more than one '%s', list "n_repolist_uses=x" (x being the number of '%s') in the cf.caching_wrapper
(3) Navigate to 8Knot/queries/registry.py. Import your new query and add it to the QUERIES list.
    this registers your query to be scheduled when a user requests new data.
(4) Create a table in 8Knot/8Knot/cache_manager/db_init.py for the new data you're retrieving from augur. Name the table identically to
    your custom "NAME_query". e.g. if your query is "num_stars_query" the table should have the same name. Detailed instructions regarding
    creating a table are in the db_init.py file.
(5) Update the docstring of the query to reflect the intention of the data being collected.
(6) Delete this list when completed

NOTE: Querying data from Augur is a Postgres->Postgres transaction. Any data transformations that will always
    apply to visualization using the same data should either:

    (a) be done in the SQL itself, so all records retrieved from Augur are usable or

    (b) become analysis pre-processing steps that run on-the-fly on user request. Utilities for this kind of
        processing are typically in 8Knot/8Knot/pages/utils/preprocessing_utils.py, but "your mileage may vary."

        If you choose this path, PLEASE DOCUMENT this behavior.
"""


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    exponential_backoff=2,
    retry_kwargs={"max_retries": 5},
    retry_jitter=True,
)
def NAME_query(self, repos):
    """
    (Worker Query)
    Executes SQL query against Augur database for GitHub data.

    Args:
    -----
        repos ([int]): repos that SQL query is executed on.

    Returns:
    --------
        dict: Results from SQL query, interpreted from pd.to_dict('records')

    """
    logging.warning(f"{NAME_query.__name__} COLLECTION - START")

    if len(repos) == 0:
        return None

    query_string = """
                    SELECT

                    FROM

                    WHERE
                        repo_id in %s
                """

    func_name = NAME_query.__name__

    # raises Exception on failure. Returns nothing.
    cf.caching_wrapper(
        func_name=func_name,
        query=query_string,
        repolist=repos,
    )

    logging.warning(f"{NAME_query.__name__} COLLECTION - END")
