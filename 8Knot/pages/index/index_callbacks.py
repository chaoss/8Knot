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
from app import augur as collectoss
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
from models import SearchItem, clean_repo_name
import redis
import flask
from sqlalchemy.exc import SQLAlchemyError

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
                        href=collectoss.user_account_endpoint,
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


def _format_search_option(opt: dict) -> dict:
    """Format a raw search option with its platform or item-type prefix."""
    formatted_opt = opt.copy()
    search_item = SearchItem.from_id(opt["value"])
    label = opt["label"]
    if search_item == SearchItem.REPO:
        cleaned_name, platform = clean_repo_name(label)
        if platform == "github":
            formatted_opt["label"] = f"GH Repo: {cleaned_name}"
        elif platform == "gitlab":
            formatted_opt["label"] = f"GL Repo: {cleaned_name}"
        else:
            formatted_opt["label"] = f"Repo: {cleaned_name}"
    else:
        formatted_opt["label"] = search_item.prefix(label)
    return formatted_opt


def _selection_options(values: list, current_options: list) -> list:
    """Retain already-formatted pill labels from the bounded dropdown data."""
    options_by_value = {opt["value"]: opt for opt in (current_options or [])}
    return [options_by_value.get(v, {"value": v, "label": SearchItem.from_id(v).prefix(str(v))}) for v in values]


@callback(
    [Output("projects", "data"), Output("projects", "nothingFoundMessage")],
    [Input("projects", "searchValue")],
    [State("projects", "value"), State("projects", "data")],
)
def dynamic_multiselect_options(user_in: str, selections, current_options):
    """
    Indexed search using PostgreSQL Full-Text Search (to_tsvector/to_tsquery)
    and trigram similarity (pg_trgm) in postgres-cache.

    Args:
        user_in: User's search input
        selections: Currently selected values
        current_options: Current bounded dropdown data, including formatted selection labels
    """
    if not user_in:
        return dash.no_update

    try:
        start_time = time.time()
        logging.info(f"Search query: '{user_in}'")

        if selections is None:
            selections = []

        # Remove prefixes from the search query if present
        search_query = user_in.strip()
        prefix_type = None

        if search_query.lower().startswith("repo:"):
            search_query = search_query[5:].strip()
            prefix_type = "repo"
            logging.info(f"Repo prefix detected, searching for: '{search_query}'")
        elif search_query.lower().startswith("org:"):
            search_query = search_query[4:].strip()
            prefix_type = "org"
            logging.info(f"Org prefix detected, searching for: '{search_query}'")

        if not search_query:
            return dash.no_update

        try:
            matched_options = cf.search_options_query(search_query, item_type=prefix_type)
        except cf.SearchOptionsEmpty:
            logging.warning("search_options is empty, re-syncing it from CollectOSS")
            cf.sync_search_options(collectoss.get_multiselect_options())
            matched_options = cf.search_options_query(search_query, item_type=prefix_type)

        user_options = []
        if current_user.is_authenticated and prefix_type != "repo":
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
                    matched_user_options = [opt for opt in user_options if search_query.lower() in opt["label"].lower()]
                    matched_options = matched_options + matched_user_options
            except redis.exceptions.ConnectionError as e:
                logging.error(f"MULTISELECT: Could not connect to users-cache. Error: {str(e)}")

        # Format options with prefixes based on their type and deduplicate
        formatted_opts = []
        seen_values = set()

        for opt in matched_options:
            if opt["value"] in seen_values:
                continue
            seen_values.add(opt["value"])
            formatted_opts.append(_format_search_option(opt))

        # Keep the search's relevance order; it already puts orgs first among equally good matches
        n_orgs = sum(SearchItem.from_id(opt["value"]) == SearchItem.ORG for opt in formatted_opts)
        n_repos = len(formatted_opts) - n_orgs

        # Always include the previous selections so active pills retain their labels
        missing_selections = [v for v in selections if v not in seen_values]
        if missing_selections:
            formatted_opts += _selection_options(missing_selections, current_options)

        end_time = time.time()
        logging.info(f"Search completed in {end_time - start_time:.4f}s: {n_orgs} orgs, {n_repos} repos")

        return formatted_opts, "No matching repos/orgs."

    except Exception:
        logging.exception("Error in dynamic_multiselect_options")
        return _selection_options(selections or [], current_options), "Search is temporarily unavailable. Please retry."


# callback for repo selections to feed into visualization call backs
@callback(
    [Output("selection-error", "children"), Output("repo-choices", "data"), Output("applied-projects", "data")],
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

    # names of CollectOSS groups or orgs
    names = [n for n in user_vals if SearchItem.from_id(n) == SearchItem.ORG]

    try:
        orgs = collectoss.resolve_org_repos(names)
    except SQLAlchemyError:
        logging.exception("SEARCH-BUTTON: Could not resolve organizations from CollectOSS")
        return (
            dbc.Alert("Unable to resolve selected organizations. Please retry.", color="warning"),
            dash.no_update,
            dash.no_update,
        )

    org_repos = [repo_id for members in orgs.values() for repo_id in members]
    logging.warning(f"ORG_REPOS: {org_repos}")

    group_names = [name for name in names if name not in orgs]
    user_groups = {}
    if group_names and current_user.is_authenticated:
        logging.warning(f"LOGINBUTTON: USER LOGGED IN {current_user}")
        # TODO: implement more permanent interface
        users_cache = redis.StrictRedis(
            host=os.getenv("REDIS_SERVICE_USERS_HOST", "redis-users"),
            port=6379,
            password=os.getenv("REDIS_PASSWORD", ""),
            decode_responses=True,
        )
        try:
            cached_groups = users_cache.get(f"{current_user.get_id()}_groups")
            if cached_groups:
                user_groups = json.loads(cached_groups)
                logging.warning(f"USERS Groups: {type(user_groups)}, {user_groups}")
        except redis.exceptions.RedisError:
            logging.error("Searchbar: couldn't connect to Redis for user group options.")
            return (
                dbc.Alert("Unable to load selected user groups. Please retry.", color="warning"),
                dash.no_update,
                dash.no_update,
            )

    if any(name not in user_groups for name in group_names):
        return (
            dbc.Alert(
                "A selected organization or group is no longer available. Refresh your selection.", color="warning"
            ),
            dash.no_update,
            dash.no_update,
        )

    group_repos = [user_groups[g] for g in group_names]
    # flatten list repo_ids in orgs to 1D
    group_repos = [v for l in group_repos for v in l]
    logging.warning(f"GROUP_REPOS: {group_repos}")

    # only unique repo ids
    all_repo_ids = list(set().union(*[repos, org_repos, group_repos]))
    logging.warning(f"SELECTED_REPOS: {all_repo_ids}")

    return "", all_repo_ids, user_vals


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
    url_list = collectoss.repo_ids_to_git(repo_ids)

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
    Executes queries defined in /queries against CollectOSS
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
# Pill colors follow the last successfully confirmed selection.
#
# This callback implements dynamic pill coloring:
# - When user selects repos/orgs: pills are red (pending)
# - Successful confirmation turns matching pills blue (active search)
# - Failed or in-flight confirmations leave changed selections red
#
# Works in conjunction with CSS in main_layout.css
# ============================================================================
@callback(
    Output("projects", "className"),
    [Input("applied-projects", "data"), Input("projects", "value")],
)
def update_pill_color_on_search(applied_values, selected_values):
    """Mark pills applied only when they match the last successful confirmation."""
    if selected_values and set(selected_values) == set(applied_values or []):
        return "searchbar-dropdown searching"
    return "searchbar-dropdown"


# Scroll the URL's #fragment graph card into view on every hash change.
# Implementation (and the reasoning for it) lives in assets/scroll_to_anchor.js.
clientside_callback(
    ClientsideFunction(namespace="eightknot", function_name="scroll_to_anchor"),
    Output("anchor-scroll-dummy", "data"),
    Input("url", "hash"),
    prevent_initial_call=False,
)
