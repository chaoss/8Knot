import logging
from app import celery_app, augur
import pandas as pd
import redis
import json
import os


@celery_app.task(
    bind=True,
)
def user_groups_query(self, user_id):
    """
    (Worker Query)
    Executes SQL query against Augur frontend for logged-in user's groups.

    Runs on-request per user. Doesn't collect data for visualization.

    Args:
    -----
        user_id (int): which user's groups we want

    Returns:
    --------
        bool: Success of getting groups
    """
    logging.warning(f"{user_groups_query.__name__} COLLECTION - START")

    users_cache = redis.StrictRedis(
        host=os.getenv("REDIS_SERVICE_USERS_HOST", "redis-users"),
        port=6379,
        password=os.getenv("REDIS_PASSWORD", ""),
    )

    # checks connection to Redis, raises redis.exceptions.ConnectionError if connection fails.
    # returns True if connection succeeds.
    users_cache.ping()

    # check if user is in sessions
    if not users_cache.exists(user_id):
        raise Exception("Expected user data under user_id not in cache.")
    else:
        user = json.loads(users_cache.get(user_id))

    # query groups and options from Augur
    users_groups, users_options = get_user_groups(user["username"], user["access_token"])

    # stores groups and options in cache
    groups_set = users_cache.set(name=f"{user_id}_groups", value=json.dumps(users_groups))
    options_set = users_cache.set(name=f"{user_id}_group_options", value=json.dumps(users_options))

    # returns success of operation
    return bool(groups_set and options_set)


def get_user_groups(username, bearer_token):
    """Requests all user-level groups from augur frontend.

    Args:
        username (str): client's username
        bearer_token (str): client's bearer token

    Returns:
        dict{group_name: [repo_ids]}: dict of users groups
        list[{group_name, group_label}]: list of dicts to translate group labels to their values.
    """

    # request to get user's groups
    augur_users_groups = augur.make_user_request(access_token=bearer_token)

    # structure of the incoming data
    # [{group_name: {favorited: False, repos: [{repo_git: asd;lfkj, repo_id=46555}, ...]}, ...]
    # creates the group_name->repo_list mapping and the searchbar options for augur user groups
    users_groups = {}
    users_group_options = []
    g = augur_users_groups.get("data")

    # each of the augur user groups
    for entry in g:
        # group has one key- the name.
        group_name: str = list(entry.keys())[0]

        # only one value per entry- {favorited: ..., repos: ...},
        # get the value component
        repo_list = list(entry.values())[0]["repos"]

        ids = parse_repolist(repo_list)

        # don't accept empty groups
        if len(ids) == 0:
            continue

        # using lower_name for convenience later- no .lower() calls
        lower_name = group_name.lower()

        # group_name->repo_list mapping
        users_groups[lower_name] = ids

        # searchbar options
        # user's groups are prefixed w/ username to guarantee uniqueness in searchbar
        users_group_options.append({"value": lower_name, "label": f"{username}: {group_name}"})

    return users_groups, users_group_options


def parse_repolist(repo_list, prepend_to_url=""):
    """Converts repo_git URLs to
    indexed repo_ids from startup for consumption
    by group_name->list_of_repo_ids.

    Args:
        repo_list ([{repo_info}]): list of repo metadata from augur frontend.
        prepend_to_url (str): string to prepend, e.g. "https://" if known not available

    Returns:
        [int]: list of repo ids identified.
    """
    # structure of the incoming data
    # [{repo_git: asd;lfkj, repo_id=46555, ...}, ...]
    # creates the group_name->repo_list mapping and the searchbar options for augur user groups

    ids = []
    for repo in repo_list:
        if "repo_git" in repo.keys():
            # user groups have URL under 'repo_git' key
            repo_url = repo.get("repo_git")
        elif "url" in repo.keys():
            # admin groups have URL under "url" key
            repo_url = repo.get("url")
        else:
            # if neither present, skip
            logging.error(f"PARSE_REPOLIST: NO REPO_URL IN OBJECT")
            continue

        # translate that natural key to the repo's ID in the primary database
        repo_id_translated = augur.repo_git_to_id(prepend_to_url + repo_url)

        # check if the translation worked.
        if not repo_id_translated:
            logging.error(f"PARSE_REPOLIST: {repo_url} NOT TRANSLATABLE TO REPO_ID")
            continue

        ids.append(repo_id_translated)

    return ids
