from datetime import datetime, timedelta
import re
import os
import time
import logging
import json
from celery.result import AsyncResult
import dash_bootstrap_components as dbc
import dash
from dash import callback, html, clientside_callback, ClientsideFunction
from dash.dependencies import Input, Output, State, MATCH
from app import augur
from flask_login import current_user
import cache_manager.cache_facade as cf
from queries.issues_query import issues_query as iq
from queries.commits_query import commits_query as cq
from queries.contributors_query import contributors_query as cnq
from queries.prs_query import prs_query as prq
from queries.affiliation_query import affiliation_query as aq
from queries.pr_assignee_query import pr_assignee_query as praq
from queries.issue_assignee_query import issue_assignee_query as iaq
from queries.user_groups_query import user_groups_query as ugq
from queries.pr_response_query import pr_response_query as prr
from queries.cntrb_per_file_query import cntrb_per_file_query as cpfq
from queries.repo_files_query import repo_files_query as rfq
from queries.pr_files_query import pr_file_query as prfq
from queries.repo_languages_query import repo_languages_query as rlq
from queries.package_version_query import package_version_query as pvq
from queries.repo_releases_query import repo_releases_query as rrq
from queries.ossf_score_query import ossf_score_query as osq
from queries.repo_info_query import repo_info_query as riq
from models import SearchItem
import redis
import flask
from .search_utils import fuzzy_search
from .search_utils import clean_repo_name

# list of queries to be run (includes codebase page queries for heatmaps)
# affiliation_query is last because its 3-way JOIN + GROUP BY is the slowest query;
# keeping it at the end lets the faster queries finish without being blocked.
QUERIES = [iq, cq, cnq, prq, iaq, praq, prr, cpfq, rfq, prfq, rlq, pvq, rrq, osq, riq, aq]


# check if login has been enabled in config
login_enabled = os.getenv("AUGUR_LOGIN_ENABLED", "False") == "True"

# Note: Login-related callbacks are conditionally registered based on login_enabled
# because when login is disabled, the UI elements (refresh-button, logout-button, etc.)
# don't exist in the layout, which would cause "nonexistent object" callback errors.


def _start_group_collection_login_enabled(url, n_clicks):
    """Schedules a Celery task to collect user groups.
    Sends a message via localStorage that will kick off a background callback
    which waits for the Celery task to finish.

    if refresh-groups clicked, forces group reload.

    Args:
        url (str): browser page URL
        n_clicks (_type_): number 'refresh_groups' button has been clicked.

    Returns:
        int: ID of Celery task that has started for group collection.
    """
    if current_user.is_authenticated:
        user_id = current_user.get_id()
        users_cache = redis.StrictRedis(
            host=os.getenv("REDIS_SERVICE_USERS_HOST", "redis-users"),
            port=6379,
            password=os.getenv("REDIS_PASSWORD", ""),
        )
        try:
            users_cache.ping()
        except redis.exceptions.ConnectionError:
            logging.error("GROUP-COLLECTION: Could not connect to users-cache.")
            return dash.no_update

        # TODO: check how old groups are. If they're pretty old (threshold tbd) then requery

        # check if groups are not already cached, or if the refresh-button was pressed
        if not users_cache.exists(f"{user_id}_groups") or (dash.ctx.triggered_id == "refresh-button"):
            # kick off celery task to collect groups
            # on query worker queue,
            return [ugq.apply_async(args=[user_id], queue="data").id]
        else:
            return dash.no_update
    else:
        # user anonymous
        return dash.no_update


def _start_group_collection_login_disabled(url):
    """Simplified version when login is disabled - no group collection needed."""
    return dash.no_update


def _login_username_button_enabled(url):
    """Sets logged-in-status component in top left of page.

    If a non-null username is known then we're logged in so we provide
    the user a button to go to Augur. Otherwise, we redirect them to login.

    This callback also sets a login_failure popover depending on whether
    a requested login succeeded.

    Args:
        username (str | None): Username of user or None
        login_succeeded (bool): Error enabled if login failed.

    Returns:
        _type_: _description_
    """

    navlink = [
        dbc.NavLink(
            "Augur log in/sign up",
            href="/login/",
            id="login-navlink",
            active=True,
            # communicating with the underlying Flask server
            external_link=True,
        ),
    ]

    buttons_disabled = True
    login_succeeded = True

    if current_user:
        if current_user.is_authenticated:
            logging.warning(f"LOGINBUTTON: USER LOGGED IN {current_user}")
            # TODO: implement more permanent interface
            users_cache = redis.StrictRedis(
                host=os.getenv("REDIS_SERVICE_USERS_HOST", "redis-users"),
                port=6379,
                password=os.getenv("REDIS_PASSWORD", ""),
            )
            try:
                users_cache.ping()
            except redis.exceptions.ConnectionError:
                logging.error("USERNAME: Could not connect to users-cache.")
                return dash.no_update

            user_id = current_user.get_id()
            user_info = json.loads(users_cache.get(user_id))

            navlink = [
                dbc.NavItem(
                    dbc.NavLink(
                        f"{user_info['username']}",
                        href=augur.user_account_endpoint,
                        id="login-navlink",
                        disabled=True,
                    ),
                ),
            ]
            buttons_disabled = False

    return (
        navlink,
        not login_succeeded,
        buttons_disabled,
        buttons_disabled,
        buttons_disabled,
    )


def _login_username_button_disabled(url):
    """Simplified version when login is disabled - just shows the login link."""
    navlink = [
        dbc.NavLink(
            "Augur log in/sign up",
            href="/login/",
            id="login-navlink",
            active=True,
            # communicating with the underlying Flask server
            external_link=True,
        ),
    ]
    return [navlink]


@callback(
    [Output("projects", "data")],
    [Input("projects", "searchValue")],
    [State("projects", "value"), State("cached-options", "data")],
)
def dynamic_multiselect_options(user_in: str, selections, cached_options):
    """
    Enhanced search using fuzzy matching and client-side cache with server fallback.

    Args:
        user_in: User's search input
        selections: Currently selected values
        cached_options: All available options from client-side cache
    """
    if not user_in:
        return dash.no_update

    try:
        start_time = time.time()
        logging.info(f"Search query: '{user_in}'")

        # Start with cached options if available
        if cached_options:
            logging.info(f"Using client-side cache with {len(cached_options)} options")
            options = cached_options
        else:
            logging.info("Client-side cache empty, fetching from server")
            options = augur.get_multiselect_options().copy()
            logging.info(f"Fetched {len(options)} options from server")
            if current_user.is_authenticated:
                try:
                    users_cache = redis.StrictRedis(
                        host=os.getenv("REDIS_SERVICE_USERS_HOST", "redis-users"),
                        port=6379,
                        password=os.getenv("REDIS_PASSWORD", ""),
                        decode_responses=True,
                    )
                    users_cache.ping()
                    if users_cache.exists(f"{current_user.get_id()}_group_options"):
                        user_options = json.loads(users_cache.get(f"{current_user.get_id()}_group_options"))
                        options = options + user_options
                        logging.info(f"Added {len(user_options)} user options from Redis")
                except redis.exceptions.ConnectionError as e:
                    logging.error(f"MULTISELECT: Could not connect to users-cache. Error: {str(e)}")

        if selections is None:
            selections = []

        # Remove prefixes from the search query if present
        search_query = user_in
        prefix_type = None

        if search_query.lower().startswith("repo:"):
            search_query = search_query[5:].strip()
            prefix_type = "repo"
            logging.info(f"Repo prefix detected, searching for: '{search_query}'")
        elif search_query.lower().startswith("org:"):
            search_query = search_query[4:].strip()
            prefix_type = "org"
            logging.info(f"Org prefix detected, searching for: '{search_query}'")

        # SEARCH STRATEGY: searching both cache and server for best results. The client-side cache is still prioritized if available.
        cache_matches = []
        server_matches = []

        # Initialize fallback flag
        use_server_fallback = False

        # Adjust threshold based on query length - more specific queries can use lower threshold
        search_threshold = 0.15 if len(search_query) >= 4 else 0.2

        # First, the search goes through the client-side cache if available
        if cached_options:
            cache_matches = fuzzy_search(search_query, cached_options, threshold=search_threshold, limit=1000)
            logging.info(f"Cache search found {len(cache_matches)} matches (threshold={search_threshold}, limit=1000)")

        # Always also search server for comprehensive results (especially for longer queries)
        if len(search_query) >= 3:
            try:
                server_options = augur.get_multiselect_options().copy()
                if current_user.is_authenticated:
                    try:
                        users_cache = redis.StrictRedis(
                            host=os.getenv("REDIS_SERVICE_USERS_HOST", "redis-users"),
                            port=6379,
                            password=os.getenv("REDIS_PASSWORD", ""),
                            decode_responses=True,
                        )
                        users_cache.ping()
                        if users_cache.exists(f"{current_user.get_id()}_group_options"):
                            user_options = json.loads(users_cache.get(f"{current_user.get_id()}_group_options"))
                            server_options = server_options + user_options
                    except redis.exceptions.ConnectionError as e:
                        logging.error(f"SERVER SEARCH: Could not connect to users-cache. Error: {str(e)}")

                server_matches = fuzzy_search(search_query, server_options, threshold=search_threshold, limit=1000)
                logging.info(
                    f"Server search found {len(server_matches)} matches (threshold={search_threshold}, limit=1000)"
                )

            except Exception as e:
                logging.error(f"Server search failed: {str(e)}")
                server_matches = []

        # If no cache available, fetch from server
        if not cached_options:
            matched_options = server_matches
            use_server_fallback = True
            logging.info(f"No cache available, using {len(server_matches)} server matches")
        else:
            # Combine cache and server results, prioritizing cache but adding server matches
            matched_options = cache_matches.copy()
            seen_values = set(opt["value"] for opt in cache_matches)
            additional_from_server = []

            for server_match in server_matches:
                if server_match["value"] not in seen_values:
                    additional_from_server.append(server_match)
                    seen_values.add(server_match["value"])

            matched_options.extend(additional_from_server)
            use_server_fallback = len(additional_from_server) > 0

            logging.info(
                f"Combined results: {len(cache_matches)} from cache + {len(additional_from_server)} from server = {len(matched_options)} total"
            )

        # Filter by prefix type if specified
        if prefix_type == "repo":
            matched_options = [opt for opt in matched_options if SearchItem.from_id(opt["value"]) == SearchItem.REPO]
            logging.info(f"Filtered to {len(matched_options)} repos")
        elif prefix_type == "org":
            matched_options = [opt for opt in matched_options if SearchItem.from_id(opt["value"]) == SearchItem.ORG]
            logging.info(f"Filtered to {len(matched_options)} orgs")

        # Format options with prefixes based on their type
        formatted_opts = []
        seen_values = set()  # Track seen values to prevent duplicates

        for opt in matched_options:
            # Skip duplicates (based on value)
            if opt["value"] in seen_values:
                continue

            seen_values.add(opt["value"])
            formatted_opt = opt.copy()
            search_item = SearchItem.from_id(opt["value"])

            # Clean repository names by removing URL prefixes
            label = opt["label"]
            if search_item == SearchItem.REPO:
                cleaned_name, platform = clean_repo_name(label)
                # Apply platform-specific prefix
                if platform == "github":
                    formatted_opt["label"] = f"GH Repo: {cleaned_name}"
                elif platform == "gitlab":
                    formatted_opt["label"] = f"GL Repo: {cleaned_name}"
                else:
                    formatted_opt["label"] = f"Repo: {cleaned_name}"
            else:
                formatted_opt["label"] = search_item.prefix(label)
            formatted_opts.append(formatted_opt)

        # Simple reordering: put organizations first, then repositories
        orgs_first = [opt for opt in formatted_opts if SearchItem.from_id(opt["value"]) == SearchItem.ORG]
        repos_after = [opt for opt in formatted_opts if SearchItem.from_id(opt["value"]) == SearchItem.REPO]
        formatted_opts = orgs_first + repos_after

        # Always include the previous selections
        # Format selected options with prefixes
        selected_options = []

        # First check if selections are in our current options (cache + any server fallback)
        current_selection_values = set(
            opt["value"] for opt in (cached_options or []) + (matched_options if use_server_fallback else [])
        )
        missing_selections = [v for v in selections if v not in current_selection_values]

        # If any selections aren't in our current options, fetch them from the server
        if missing_selections:
            logging.info(f"Fetching {len(missing_selections)} missing selections from server")
            all_options = augur.get_multiselect_options().copy()
            for v in selections:
                matched_opts = [opt for opt in all_options if opt["value"] == v]
                if matched_opts:
                    formatted_v = matched_opts[0].copy()
                    if SearchItem.from_id(v) == SearchItem.ORG:
                        # It's an org
                        formatted_v["label"] = f"org: {formatted_v['label']}"
                    elif SearchItem.from_id(v) == SearchItem.REPO:
                        # It's a repo
                        formatted_v["label"] = f"repo: {formatted_v['label']}"
                    selected_options.append(formatted_v)
        else:
            # All selections are in our current options
            all_current_options = (cached_options or []) + matched_options
            for v in selections:
                for opt in all_current_options:
                    if opt["value"] == v:
                        formatted_v = opt.copy()
                        search_item = SearchItem.from_id(v)
                        formatted_v["label"] = search_item.prefix(opt["label"])
                        selected_options.append(formatted_v)
                        break

        # NO LIMITS for now: Return all matches with orgs prioritized
        # Use the org/repo separation already done

        logging.info(
            f"Final results breakdown: {len(orgs_first)} orgs, {len(repos_after)} repos, {len(formatted_opts)} total"
        )

        # Always prioritize orgs first, then repos, but don't limit the total count
        result = orgs_first + repos_after

        # Add selected options that aren't already in the results
        selected_values = [opt["value"] for opt in result]
        for opt in selected_options:
            if opt["value"] not in selected_values:
                result.append(opt)

        end_time = time.time()
        logging.info(f"Search completed in {end_time - start_time:.2f} seconds")
        logging.info(f"Returning {len(result)} options to dropdown (fallback used: {use_server_fallback})")

        return [result]

    except Exception as e:
        logging.error(f"Error in dynamic_multiselect_options: {str(e)}")
        # Return at least the current selections as a fallback
        if selections:
            default_options = []
            try:
                # Try to get the labels for the current selections
                options = augur.get_multiselect_options()
                for v in options:
                    if v["value"] in selections:
                        formatted_v = v.copy()
                        search_item = SearchItem.from_id(v)
                        if search_item == SearchItem.ORG:
                            formatted_v["label"] = f"org: {v['label']}"
                        elif search_item == SearchItem.REPO:
                            formatted_v["label"] = f"repo: {v['label']}"
                        default_options.append(formatted_v)
            except:
                # If that fails, just return the raw selection values
                default_options = [{"value": v, "label": f"ID: {v}"} for v in selections]

            return [default_options]

        return dash.no_update


# callback for repo selections to feed into visualization call backs
@callback(
    [Output("results-output-container", "children"), Output("repo-choices", "data")],
    [
        Input("search-button", "n_clicks"),
        State("projects", "value"),
    ],
)
def multiselect_values_to_repo_ids(search_button_clicks, user_vals):
    if not user_vals:
        logging.warning("NOTHING SELECTED IN SEARCH BAR")
        raise dash.exceptions.PreventUpdate

    # individual repo numbers
    repos = [int(r) for r in user_vals if SearchItem.from_id(r) == SearchItem.REPO]
    logging.warning(f"REPOS: {repos}")

    # names of augur groups or orgs
    names = [n for n in user_vals if SearchItem.from_id(n) == SearchItem.ORG]

    org_repos = [augur.org_to_repos(o) for o in names if augur.is_org(o)]
    # flatten list repo_ids in orgs to 1D
    org_repos = [v for l in org_repos for v in l]
    logging.warning(f"ORG_REPOS: {org_repos}")

    user_groups = []
    if current_user.is_authenticated:
        logging.warning(f"LOGINBUTTON: USER LOGGED IN {current_user}")
        # TODO: implement more permanent interface
        users_cache = redis.StrictRedis(
            host=os.getenv("REDIS_SERVICE_USERS_HOST", "redis-users"),
            port=6379,
            password=os.getenv("REDIS_PASSWORD", ""),
            decode_responses=True,
        )
        try:
            users_cache.ping()
        except redis.exceptions.ConnectionError:
            logging.error("SEARCH-BUTTON: Could not connect to users-cache.")
            return dash.no_update

        try:
            if users_cache.exists(f"{current_user.get_id()}_groups"):
                user_groups = json.loads(users_cache.get(f"{current_user.get_id()}_groups"))
                logging.warning(f"USERS Groups: {type(user_groups)}, {user_groups}")
        except redis.exceptions.ConnectionError:
            logging.error("Searchbar: couldn't connect to Redis for user group options.")

    group_repos = [user_groups[g] for g in names if not augur.is_org(g)]
    # flatten list repo_ids in orgs to 1D
    group_repos = [v for l in group_repos for v in l]
    logging.warning(f"GROUP_REPOS: {group_repos}")

    # only unique repo ids
    all_repo_ids = list(set().union(*[repos, org_repos, group_repos]))
    logging.warning(f"SELECTED_REPOS: {all_repo_ids}")

    return "", all_repo_ids


@callback(
    Output("help-alert", "is_open"),
    Input("search-help", "n_clicks"),
    State("help-alert", "is_open"),
)
def show_help_alert(n_clicks, openness):
    """Sets the 'open' state of a help message
    for the search bar to encourage users to check
    their spelling and to ask for data to be loaded
    if not available.

    Args:
        n_clicks (int): number of times 'help' button clicked.
        openness (boolean): whether help alert is currently open.

    Returns:
        dash.no_update | boolean: whether the help alert should be open.
    """
    if n_clicks == 0:
        return dash.no_update
    # switch the openness parameter, allows button to also
    # dismiss the Alert.
    return not openness


@callback(
    [Output("repo-list-alert", "is_open"), Output("repo-list-alert", "children")],
    [Input("repo-list-button", "n_clicks")],
    [State("repo-list-alert", "is_open"), State("repo-choices", "data")],
)
def show_repolist_alert(n_clicks, openness, repo_ids):
    """Sets the 'open' state of a help message
    for the search bar to encourage users to check
    their spelling and to ask for data to be loaded
    if not available.
    Args:
        n_clicks (int): number of times 'help' button clicked.
        openness (boolean): whether help alert is currently open.
    Returns:
        dash.no_update | boolean: whether the help alert should be open.
    """
    print(repo_ids)
    url_list = [augur.repo_id_to_git(i) for i in repo_ids]

    url_list = [l[8:] if l.startswith("https://") else l for l in url_list]

    element_list = [html.Li(l) for l in url_list]

    elements = [html.Strong("Included Repositories:"), html.Ul(element_list)]

    if n_clicks == 0:
        return dash.no_update, elements
    # switch the openness parameter, allows button to also
    # dismiss the Alert.
    return not openness, elements


@callback(
    [Output("data-badge", "children"), Output("data-badge", "color")],
    Input("job-ids", "data"),
    background=True,
)
def wait_queries(job_ids):
    # TODO add docstring to function

    jobs = [AsyncResult(j_id) for j_id in job_ids]

    # Add timeout protection to prevent infinite waiting
    start_time = time.time()
    max_wait_time = 600  # 10 minutes timeout

    # default 'result_expires' for celery config is 86400 seconds.
    # so we don't have to check if the jobs exist. if this tasks
    # is enqueued 24 hours after the query-worker tasks finish
    # then we have a big problem. However, we should 'forget' all
    # results before we exit.

    while True:
        # Check for timeout to prevent SoftTimeLimitExceeded
        if time.time() - start_time > max_wait_time:
            logging.warning(f"wait_queries: Timeout after {max_wait_time}s - returning timeout status")
            jobs = [j.forget() for j in jobs]
            return "Timeout - Retry", "warning"

        logging.warning([(j.name, j.status) for j in jobs])

        # jobs are either all ready
        if all(j.successful() for j in jobs):
            logging.warning([(j.name, j.status) for j in jobs])
            jobs = [j.forget() for j in jobs]
            return "Data Ready", "#0F5880"

        # or one of them has failed
        if any(j.failed() for j in jobs):
            # if a job fails, we need to wait for the others to finish before
            # we can 'forget' them. otherwise to-be-successful jobs will always
            # be forgotten if one fails.

            # tasks need to have either failed or succeeded before being forgotten.
            while True:
                num_succeeded = [j.successful() for j in jobs].count(True)
                num_failed = [j.failed() for j in jobs].count(True)
                num_total = num_failed + num_succeeded

                if num_total == len(jobs):
                    break

                time.sleep(4.0)

            jobs = [j.forget() for j in jobs]
            return "Data Incomplete- Retry", "danger"

        # pause to let something change
        time.sleep(2.0)


@callback(
    Output("job-ids", "data"),
    Input("repo-choices", "data"),
)
def run_queries(repos):
    """
    Executes queries defined in /queries against Augur
    instance for input Repos; caches results in Postgres.

    Args:
        repos ([int]): repositories we collect data for.
    """

    # list of queries to process
    funcs = QUERIES

    # list of job promises
    jobs = []

    for f in funcs:
        # only download repos that aren't currently in cache
        not_ready = cf.get_uncached(f.__name__, repos)
        if len(not_ready) == 0:
            logging.warning(f"{f.__name__} - NO DISPATCH - ALL REPOS IN CACHE")
            continue

        # add job to queue
        j = f.apply_async(args=[not_ready], queue="data")

        # add job promise to local promise list
        jobs.append(j)

    return [j.id for j in jobs]


# Add a cache initialization callback that runs on page load
@callback(
    Output("cached-options", "data"),
    Input("cache-init-trigger", "children"),  # Dummy input to trigger on page load
    prevent_initial_call=False,
)
def initialize_cache(_):
    """
    Initialize the client-side cache with all options.
    This runs once when the page loads.
    """
    try:
        logging.info("Initializing client-side options cache")
        options = augur.get_multiselect_options().copy()
        logging.info(f"Retrieved {len(options)} options from augur")

        if current_user.is_authenticated:
            try:
                users_cache = redis.StrictRedis(
                    host=os.getenv("REDIS_SERVICE_USERS_HOST", "redis-users"),
                    port=6379,
                    password=os.getenv("REDIS_PASSWORD", ""),
                    decode_responses=True,
                )
                users_cache.ping()

                if users_cache.exists(f"{current_user.get_id()}_group_options"):
                    user_options = json.loads(users_cache.get(f"{current_user.get_id()}_group_options"))
                    options = options + user_options
                    logging.info(f"Added {len(user_options)} user-specific options from Redis")
            except redis.exceptions.ConnectionError as e:
                logging.error(f"CACHE INIT: Could not connect to users-cache. Error: {str(e)}")

        # Get configuration from environment variables with defaults
        # Larger cache = faster search results (browser sessionStorage handles 20,000+ items easily)
        sort_method = os.getenv("EIGHTKNOT_SEARCHBAR_OPTS_SORT", "shortest").lower()
        max_total_results = int(os.getenv("EIGHTKNOT_SEARCHBAR_OPTS_MAX_RESULTS", "20000"))
        max_repos = int(os.getenv("EIGHTKNOT_SEARCHBAR_OPTS_MAX_REPOS", "19500"))

        # Sort options based on configuration
        if sort_method == "shortest":
            # Sort by label length to prioritize shorter names (default)
            options.sort(key=lambda x: len(x.get("label", "")))
        elif sort_method == "longest":
            # Sort by label length in reverse to prioritize longer names
            options.sort(key=lambda x: -len(x.get("label", "")))
        elif sort_method == "alphabetical":
            # Sort alphabetically
            options.sort(key=lambda x: x.get("label", "").lower())

        # For repos, keep the configured maximum number
        repos = [opt for opt in options if SearchItem.from_id(opt.get("value")) == SearchItem.REPO][:max_repos]

        # For orgs, keep all (there are usually only a few hundred)
        orgs = [opt for opt in options if SearchItem.from_id(opt.get("value")) == SearchItem.ORG]

        # Combine and prepare for storage, limiting to max_total_results
        minimal_options = (repos + orgs)[:max_total_results]

        logging.info(f"Cache initialized with {len(minimal_options)} total options (reduced from {len(options)})")
        return minimal_options
    except Exception as e:
        logging.error(f"Cache initialization failed: {str(e)}")
        # Return an empty list as a fallback to prevent complete failure
        return []


# Add search status indicator callbacks
@callback(
    [Output("search-status", "children"), Output("search-status", "className"), Output("search-status", "style")],
    [Input("projects", "searchValue")],
    prevent_initial_call=True,
)
def update_search_status(search_value):
    """Update the search status indicator when a search is performed."""
    if search_value and len(search_value) > 0:
        return ["Searching...", "search-status-indicator searching", {"display": "block"}]
    return ["", "search-status-indicator", {"display": "none"}]


# Callback to hide the search status when results are loaded
@callback(
    [Output("search-status", "style", allow_duplicate=True)], [Input("projects", "data")], prevent_initial_call=True
)
def hide_search_status_when_loaded(_):
    """Hide the search status indicator when results are loaded."""
    return [{"display": "none"}]


# =============================================================================
# CONDITIONAL CALLBACK REGISTRATION
# =============================================================================
# When login is disabled, the UI elements referenced by these callbacks
# (refresh-button, logout-button, # manage-group-button, login-popover)
# do not exist in the layout, which would
# cause "nonexistent object was used in an Input" callback errors.
#
# This conditional registration prevents those errors by only registering
# callbacks for UI elements that actually exist in the current configuration.
# =============================================================================

if login_enabled:
    # Register callbacks with full login functionality
    callback(
        [Output("user-group-loading-signal", "data")],
        [Input("url", "href"), Input("refresh-button", "n_clicks")],
    )(_start_group_collection_login_enabled)

    callback(
        [
            Output("nav-login-container", "children"),
            Output("login-popover", "is_open"),
            Output("refresh-button", "disabled"),
            Output("logout-button", "disabled"),
            Output("manage-group-button", "disabled"),
        ],
        Input("url", "href"),
    )(_login_username_button_enabled)
else:
    # Register simplified callbacks when login is disabled
    callback(
        [Output("user-group-loading-signal", "data")],
        [Input("url", "href")],
    )(_start_group_collection_login_disabled)

    callback(
        [Output("nav-login-container", "children")],
        Input("url", "href"),
    )(_login_username_button_disabled)


# Callback to handle sidebar collapse/expand functionality using dbc.Collapse
@callback(
    Output("sidebar-collapse", "is_open"),
    [Input("sidebar-toggle", "n_clicks"), Input("url", "pathname")],
    State("sidebar-collapse", "is_open"),
    prevent_initial_call=True,
)
def toggle_sidebar_collapse(n_clicks, pathname, is_open):
    """Toggle the sidebar using dbc.Collapse component and auto-open for visualization pages."""
    ctx = dash.callback_context

    # Check which input triggered the callback
    if ctx.triggered_id == "sidebar-toggle" and n_clicks:
        # Manual toggle - simply toggle the collapse state
        return not is_open
    elif ctx.triggered_id == "url":
        # URL change - check if we should auto-open for visualization pages
        visualization_paths = [
            "/repo_overview",
            "/contributions",
            "/contributors/behavior",
            "/contributors/contribution_types",
            "/affiliation",
            "/chaoss",
        ]

        # Check if current path starts with any visualization path
        should_open = any(pathname.startswith(path) for path in visualization_paths if pathname)

        if should_open and not is_open:
            return True

    return dash.no_update


# Callback to adjust main content area when sidebar state changes
@callback(
    Output("page-container", "style"),
    Input("sidebar-collapse", "is_open"),
    prevent_initial_call=True,
)
def adjust_content_area_collapse(is_open):
    """Adjust the main content area styling based on sidebar collapse state."""
    # Base styling that doesn't change
    base_style = {
        "background-color": "#1D1D1D",
        "padding": "1rem",  # Restore normal padding
        "overflow-y": "auto",
        "height": "100%",
        "flex": "1",
        "transition": "border-radius 0.3s ease",
    }

    # Only modify the border-radius based on sidebar state
    if not is_open:
        # When sidebar is collapsed, content area takes full width with rounded corners
        base_style["border-radius"] = "12px"
    else:
        # When sidebar is expanded, content area has right-side border radius only
        base_style["border-radius"] = "0 12px 12px 0"

    return base_style


# Callback to hide loading components on landing page
@callback(
    [
        Output("results-output-container", "style"),
        Output("data-badge", "style"),
    ],
    Input("url", "pathname"),
    prevent_initial_call=False,
)
def hide_loading_on_landing(pathname):
    """Hide loading components when on landing page."""
    if pathname == "/" or pathname is None:
        # Hide loading components on landing page
        return {"display": "none"}, {"display": "none"}
    else:
        # Show loading components on other pages
        return {"display": "block"}, {"marginBottom": ".5%", "display": "inline-block"}


# Note: Landing page callbacks moved to pages/landing/landing_callbacks.py


# ============================================================================
# Callback to change pill color when search is clicked
#
# This callback implements dynamic pill coloring:
# - When user selects repos/orgs: pills are red (pending)
# - When user clicks search icon: pills turn blue (active search)
# - Default selection (chaoss) starts blue since search is auto-triggered
#
# Works in conjunction with CSS in main_layout.css
# ============================================================================
@callback(
    Output("projects", "className"),
    [Input("search-button", "n_clicks"), Input("projects", "value")],
    prevent_initial_call=True,
)
def update_pill_color_on_search(search_button_clicks, selected_repos_orgs):
    """Update pill color based on search action.

    When search icon is clicked, add 'searching' class to turn pills blue.
    When values change (user is selecting), remove 'searching' class to keep pills red.
    """
    if not dash.ctx.triggered:
        return dash.no_update

    # Both inputs can change in one update (a shared link sets the selection
    # AND triggers the search); the search button wins -> pills show blue.
    triggered_ids = {t["prop_id"].split(".")[0] for t in dash.ctx.triggered}

    if "search-button" in triggered_ids:
        # Search performed - add 'searching' class to turn pills blue
        logging.info(f"PILL COLOR: Search triggered - turning pills BLUE")
        return "searchbar-dropdown searching"
    if "projects" in triggered_ids:
        # Values changed (user selecting) - remove 'searching' class to keep pills red
        logging.info(f"PILL COLOR: Values changed - turning pills RED. Selected: {selected_repos_orgs}")
        return "searchbar-dropdown"

    return dash.no_update


# Scroll the URL's #fragment graph card into view on every hash change.
# Implementation (and the reasoning for it) lives in assets/scroll_to_anchor.js.
clientside_callback(
    ClientsideFunction(namespace="eightknot", function_name="scroll_to_anchor"),
    Output("anchor-scroll-dummy", "data"),
    Input("url", "hash"),
    prevent_initial_call=False,
)
