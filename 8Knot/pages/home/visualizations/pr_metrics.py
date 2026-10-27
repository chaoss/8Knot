from dash import html, dcc
import dash_bootstrap_components as dbc
from dash import callback
from dash.dependencies import Input, Output, State
import pandas as pd
import numpy as np
import logging
from db_manager.collectoss_manager import CollectOSSManager

# card for number of open prs in the selected repo set
pr_open = dbc.Card(
    [
        dbc.CardHeader(
            html.H5(
                [html.I(className="fa-solid fa-code-pull-request"), "Open"],
                className="glace_headers",
            ),
        ),
        dbc.CardBody(
            [
                dcc.Loading(
                    children=[html.H4(id="open-pr-count", className="metric_data")],
                ),
            ],
        ),
    ],
    className="box_emissions",
)

# card for number of merged prs in the selected repo set
pr_merged = dbc.Card(
    [
        dbc.CardHeader(
            html.H5(
                [html.I(className="fa-solid fa-code-pull-request"), "Merged"],
                className="glace_headers",
            ),
        ),
        dbc.CardBody(
            [
                dcc.Loading(
                    children=[html.H4(id="merged-pr-count", className="metric_data")],
                ),
            ],
        ),
    ],
    className="box_emissions",
)

# card for number of closed prs in the selected repo set
pr_closed = dbc.Card(
    [
        dbc.CardHeader(
            html.H5(
                [html.I(className="fa-solid fa-code-pull-request"), "Closed"],
                className="glace_headers",
            ),
        ),
        dbc.CardBody(
            [
                dcc.Loading(
                    children=[html.H4(id="rejected-pr-count", className="metric_data")],
                ),
            ],
        ),
    ],
    className="box_emissions",
)

# card for average age for currently opened prs in the selected repos
pr_open_age = dbc.Card(
    [
        dbc.CardHeader(
            html.H5(
                [html.I(className="fa-solid fa-code-pull-request"), "Avg. Age of Open"],
                className="glace_headers",
            ),
        ),
        dbc.CardBody(
            [
                dcc.Loading(
                    children=[html.H4(id="avg-open-pr-age", className="metric_data")],
                ),
            ],
        ),
    ],
    className="box_emissions",
)

# card for average time to merged for merged prs in the selected repos
pr_merged_age = dbc.Card(
    [
        dbc.CardHeader(
            html.H5(
                [
                    html.I(className="fa-solid fa-code-pull-request"),
                    "Avg. Lifespan of Merged",
                ],
                className="glace_headers",
            ),
        ),
        dbc.CardBody(
            [
                dcc.Loading(
                    children=[html.H4(id="avg-merged-pr-age", className="metric_data")],
                ),
            ],
        ),
    ],
    className="box_emissions",
)

# card for average number of messages for each pr in the selected repos
pr_messages = dbc.Card(
    [
        dbc.CardHeader(
            html.H5(
                [html.I(className="fa-solid fa-code-pull-request"), "Avg. # Messages"],
                className="glace_headers",
            ),
        ),
        dbc.CardBody(
            [
                dcc.Loading(
                    children=[html.H4(id="avg-pr-messages", className="metric_data")],
                ),
            ],
        ),
    ],
    className="box_emissions",
)

gc_pr_metrics = dbc.Card(
    [
        dbc.CardBody(
            [
                html.H2(
                    [
                        html.I(className="fa-solid fa-code-pull-request"),
                        "Pull Requests",
                    ],
                    className="card-title",
                    style={"textAlign": "center"},
                ),
                html.Br(),
                dbc.Row(
                    [
                        dbc.Col(pr_open, width=3),
                        dbc.Col(pr_merged, width=3),
                        dbc.Col(pr_closed, width=3),
                        dbc.Col(pr_messages, width=3),
                    ],
                    justify="between",
                ),
                dbc.Row(
                    [
                        dbc.Col(pr_open_age, width=3),
                        dbc.Col(pr_merged_age, width=3),
                    ],
                    justify="around",
                ),
            ],
        ),
    ],
)


# callbacks below are for the specific queries for these cards
@callback(
    Output("open-pr-count", "children"),
    [
        Input("repo-choices", "data"),
    ],
    background=True,
)
def pr_count(repolist):
    """Queries Augur for the count of open prs for repos in repolist
    Args:
        repolist ([int]): list of the repos queried
    """

    # create CollectOSSManager using credentials from the environment
    db = CollectOSSManager()

    # create engine object from creds
    db.get_engine()

    # run query
    df = db.run_query(
        f"""
        select
            count(distinct pr.pull_request_id) as num_open_prs
        from
            pull_requests pr,
            repo r
        where
            r.repo_id in ({str(repolist)[1:-1]})
            and pr.repo_id = r.repo_id
            and pr.pr_closed_at is null
        """
    )

    return df.iat[0, 0]


@callback(
    Output("merged-pr-count", "children"),
    [
        Input("repo-choices", "data"),
    ],
    background=True,
)
def merged_pr_count(repolist):
    """Queries Augur for the count of merged prs for repos in repolist
    Args:
        repolist ([int]): list of the repos queried
    """

    # create CollectOSSManager using credentials from the environment
    db = CollectOSSManager()

    # create engine object from creds
    db.get_engine()

    # run query
    df = db.run_query(
        f"""
        select
            count(distinct pr.pull_request_id) as num_open_prs
        from
            pull_requests pr,
            repo r
        where
            r.repo_id in ({str(repolist)[1:-1]})
            and pr.repo_id = r.repo_id
            and pr.pr_merged_at is not null
        """
    )

    return df.iat[0, 0]


@callback(
    Output("rejected-pr-count", "children"),
    [
        Input("repo-choices", "data"),
    ],
    background=True,
)
def rejected_pr_count(repolist):
    """Queries Augur for the count of unmerged but closed prs for repos in repolist
    Args:
        repolist ([int]): list of the repos queried
    """

    # create CollectOSSManager using credentials from the environment
    db = CollectOSSManager()

    # create engine object from creds
    db.get_engine()

    # run query
    df = db.run_query(
        f"""
        select
            count(distinct pr.pull_request_id) as num_open_prs
        from
            pull_requests pr,
            repo r
        where
            r.repo_id in ({str(repolist)[1:-1]})
            and pr.repo_id = r.repo_id
            and pr.pr_merged_at is null
            and pr.pr_closed_at is not null
        """
    )

    return df.iat[0, 0]


@callback(
    Output("avg-open-pr-age", "children"),
    [
        Input("repo-choices", "data"),
    ],
    background=True,
)
def avg_open_pr_age(repolist):
    """Queries Augur for the average age of open PRs for repos in repolist
    Args:
        repolist ([int]): list of the repos queried
    """

    # create CollectOSSManager using credentials from the environment
    db = CollectOSSManager()

    # create engine object from creds
    db.get_engine()

    # run query
    df = db.run_query(
        f"""
        select
            avg(now() - pr.pr_created_at) as difference
        from
            pull_requests pr,
            repo r
        where
            r.repo_id in ({str(repolist)[1:-1]})
            and pr.repo_id = r.repo_id
            and pr.pr_closed_at is null
        """
    )

    # timedelta object
    diff = df.iat[0, 0]

    # days component
    diff_days = diff.days

    # timedelta representation of # of days to get hours
    days_delta = pd.Timedelta(days=diff_days)

    # gives remaining hours
    diff_hours = (diff - days_delta) / np.timedelta64(1, "h")

    return f"{diff_days} days, {round(diff_hours, 1)} hours"


@callback(
    Output("avg-merged-pr-age", "children"),
    [
        Input("repo-choices", "data"),
    ],
    background=True,
)
def avg_merged_pr_age(repolist):
    """Queries Augur for the average age of merged PRs for repos in repolist
    Args:
        repolist ([int]): list of the repos queried
    """

    # create CollectOSSManager using credentials from the environment
    db = CollectOSSManager()

    # create engine object from creds
    db.get_engine()

    # run query
    df = db.run_query(
        f"""
        select
            avg(pr.pr_merged_at - pr.pr_created_at) as difference
        from
            pull_requests pr,
            repo r
        where
            r.repo_id in ({str(repolist)[1:-1]})
            and pr.repo_id = r.repo_id
            and pr.pr_closed_at is not null
            and pr.pr_merged_at is not null
        """
    )

    # timedelta object
    diff = df.iat[0, 0]

    # days component
    diff_days = diff.days

    # timedelta representation of # of days to get hours
    days_delta = pd.Timedelta(days=diff_days)

    # gives remaining hours
    diff_hours = (diff - days_delta) / np.timedelta64(1, "h")

    return f"{diff_days} days, {round(diff_hours, 1)} hours"


@callback(
    Output("avg-pr-messages", "children"),
    [
        Input("repo-choices", "data"),
    ],
    background=True,
)
def rejected_pr_count(repolist):
    """Queries Augur for the average # of messages on all PRs for repos in repolist
    Args:
        repolist ([int]): list of the repos queried
    """

    # create CollectOSSManager using credentials from the environment
    db = CollectOSSManager()

    # create engine object from creds
    db.get_engine()

    # run query
    df = db.run_query(
        f"""
        select
            avg(prmc.message_count) as avg_message_count
        from
            /*
            * count the number of unique message ID's for each PR
            * */
            (select
                count(distinct prmr.msg_id) message_count
            from
                pull_requests pr,
                pull_request_message_ref prmr,
                repo r
            where
                r.repo_id in ({str(repolist)[1:-1]})
                and pr.repo_id = r.repo_id
                and prmr.pull_request_id = pr.pull_request_id
            group by pr.pull_request_id
            ) as prmc
        """
    )

    return round(df.iat[0, 0], 2)
