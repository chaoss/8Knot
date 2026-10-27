from dash import html, dcc
import dash_bootstrap_components as dbc
from dash import callback
from dash.dependencies import Input, Output, State
from db_manager.collectoss_manager import CollectOSSManager
import numpy as np
import pandas as pd


# card for number of open issues in the selected repo set
issue_open = dbc.Card(
    [
        dbc.CardHeader(
            html.H5(
                [html.I(className="fa-regular fa-circle-dot"), "Open"],
                className="glace_headers",
            ),
        ),
        dbc.CardBody(
            [
                dcc.Loading(
                    children=[html.H4(id="open-issue-count", className="metric_data")],
                ),
            ],
        ),
    ],
    className="box_emissions",
)

# card for total issues closed in the repo set
issue_closed = dbc.Card(
    [
        dbc.CardHeader(
            html.H5(
                [html.I(className="fa-regular fa-circle-dot"), "Closed"],
                className="glace_headers",
            ),
        ),
        dbc.CardBody(
            [
                dcc.Loading(
                    children=[html.H4(id="closed-issue-count", className="metric_data")],
                ),
            ],
        ),
    ],
    className="box_emissions",
)

# card for average age for currently opened issues in the selected repos
issue_open_age = dbc.Card(
    [
        dbc.CardHeader(
            html.H5(
                [html.I(className="fa-regular fa-circle-dot"), "Avg. Age of Open"],
                className="glace_headers",
            ),
        ),
        dbc.CardBody(
            [
                dcc.Loading(
                    children=[html.H4(id="avg-open-issue-age", className="metric_data")],
                ),
            ],
        ),
    ],
    className="box_emissions",
)

# card for average amount of time a closed issue was open in the selected repos
issue_closed_age = dbc.Card(
    [
        dbc.CardHeader(
            html.H5(
                [html.I(className="fa-regular fa-circle-dot"), "Avg. Age of Closed"],
                className="glace_headers",
            ),
        ),
        dbc.CardBody(
            [
                dcc.Loading(
                    children=[html.H4(id="avg-closed-issue-age", className="metric_data")],
                ),
            ],
        ),
    ],
    className="box_emissions",
)


gc_issue_metrics = dbc.Card(
    [
        dbc.CardBody(
            [
                html.H2(
                    [html.I(className="fa-regular fa-circle-dot"), "Issues"],
                    className="card-title",
                    style={"textAlign": "center"},
                ),
                html.Br(),
                dbc.Row(
                    [
                        dbc.Col(issue_open, width=3),
                        dbc.Col(issue_closed, width=3),
                        dbc.Col(issue_open_age, width=3),
                        dbc.Col(issue_closed_age, width=3),
                    ]
                ),
            ],
        ),
    ],
)

# callbacks below are for the specific queries for these cards


@callback(
    Output("avg-closed-issue-age", "children"),
    [
        Input("repo-choices", "data"),
    ],
    background=True,
)
def avg_closed_issue_age(repolist):
    """Queries Augur for the avg age of closed issues for repos in repolist
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
            avg(now() - i.created_at) as difference
        from
            issues i,
            repo r
        where
            r.repo_id in ({str(repolist)[1:-1]})
            and i.repo_id = r.repo_id
            and i.closed_at is not null
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
    Output("avg-open-issue-age", "children"),
    [
        Input("repo-choices", "data"),
    ],
    background=True,
)
def avg_open_issue_age(repolist):
    """Queries Augur for the avg age of open issues for repos in repolist
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
            avg(now() - i.created_at) as difference
        from
            issues i,
            repo r
        where
            r.repo_id in ({str(repolist)[1:-1]})
            and i.repo_id = r.repo_id
            and i.closed_at is null
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
    Output("closed-issue-count", "children"),
    [
        Input("repo-choices", "data"),
    ],
    background=True,
)
def closed_issue_count(repolist):
    """Queries Augur for the count of closed issues for repos in repolist
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
            count(distinct i.issue_id) as num_open_issues
        from
            issues i,
            repo r
        where
            r.repo_id in ({str(repolist)[1:-1]})
            and i.repo_id = r.repo_id
            and i.closed_at is not null
        """
    )

    return df.iat[0, 0]


@callback(
    Output("open-issue-count", "children"),
    [
        Input("repo-choices", "data"),
    ],
    background=True,
)
def open_issue_count(repolist):
    """Queries Augur for the count of open issues for repos in repolist
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
            count(distinct i.issue_id) as num_open_issues
        from
            issues i,
            repo r
        where
            r.repo_id in ({str(repolist)[1:-1]})
            and i.repo_id = r.repo_id
            and i.closed_at is null
        """
    )

    return df.iat[0, 0]
