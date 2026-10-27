from dash import html, dcc
import dash_bootstrap_components as dbc
from dash import callback
from dash.dependencies import Input, Output, State
from db_manager.collectoss_manager import CollectOSSManager

# card for commit total for selected repos
commit_total = dbc.Card(
    [
        dbc.CardHeader(
            html.H5(
                [html.I(className="fa-solid fa-code-commit"), "Total #"],
                className="glace_headers",
            ),
        ),
        dbc.CardBody(
            [
                dcc.Loading(
                    children=[html.H4(id="commit-count", className="metric_data")],
                ),
            ],
        ),
    ],
    className="box_emissions",
)

# card for average number of lines added per commit for selected repos
commit_lines_added = dbc.Card(
    [
        dbc.CardHeader(
            html.H5(
                [html.I(className="fa-solid fa-code-commit"), "Avg. Added Lines"],
                className="glace_headers",
            ),
        ),
        dbc.CardBody(
            [
                dcc.Loading(
                    children=[html.H4(id="commit-lines-added", className="metric_data")],
                ),
            ],
        ),
    ],
    className="box_emissions",
)

# card for average number of lines removed per commit for selected repos
commit_lines_removed = dbc.Card(
    [
        dbc.CardHeader(
            html.H5(
                [html.I(className="fa-solid fa-code-commit"), "Avg. Removed Lines"],
                className="glace_headers",
            ),
        ),
        dbc.CardBody(
            [
                dcc.Loading(
                    children=[html.H4(id="commit-lines-removed", className="metric_data")],
                ),
            ],
        ),
    ],
    className="box_emissions",
)

# card for average number of files changed per commit for selected repos
commit_files = dbc.Card(
    [
        dbc.CardHeader(
            html.H5(
                [html.I(className="fa-solid fa-code-commit"), "Avg. # Files"],
                className="glace_headers",
            ),
        ),
        dbc.CardBody(
            [
                dcc.Loading(
                    children=[html.H4(id="files-per-commit", className="metric_data")],
                ),
            ],
        ),
    ],
    className="box_emissions",
)


gc_commit_metrics = dbc.Card(
    [
        dbc.CardBody(
            [
                html.H2(
                    [html.I(className="fa-solid fa-code-commit"), "Commits"],
                    className="card-title",
                    style={"textAlign": "center"},
                ),
                html.Br(),
                dbc.Row(
                    [
                        dbc.Col(commit_total, width=3),
                        dbc.Col(commit_lines_added, width=3),
                        dbc.Col(commit_lines_removed, width=3),
                        dbc.Col(commit_files, width=3),
                    ]
                ),
            ],
        ),
    ],
)


# callbacks below are for the specific queries for these cards


@callback(
    Output("commit-count", "children"),
    [
        Input("repo-choices", "data"),
    ],
    background=True,
)
def commit_count(repolist):
    """Queries Augur for the count of commits for repos in repolist
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
            /*commit_hash'es are unique per commit*/
            count(distinct c.cmt_commit_hash) as num_commits
        from
            commits c,
            repo r
        where
            r.repo_id in ({str(repolist)[1:-1]})
            and c.repo_id = r.repo_id
        """
    )

    return df.iat[0, 0]


@callback(
    Output("commit-lines-added", "children"),
    Output("commit-lines-removed", "children"),
    [
        Input("repo-choices", "data"),
    ],
    background=True,
)
def commit_lines_delta(repolist):
    """Queries Augur for the average number of lines added per commit
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
                round(avg(l_delta.lines_added), 2) as avg_lines_added, round(avg(l_delta.lines_removed), 2) as avg_lines_removed
            from
                /*
                * For each commit, get the total number of lines added/removed across all files in commit.
                * */
                (select
                    sum(c.cmt_added) as lines_added, sum(c.cmt_removed) as lines_removed
                from
                    commits c,
                    repo r
                where
                    r.repo_id in ({str(repolist)[1:-1]})
                    and c.repo_id = r.repo_id
                group by c.cmt_commit_hash) as l_delta
        """
    )

    return df.iat[0, 0], df.iat[0, 1]


@callback(
    Output("files-per-commit", "children"),
    [
        Input("repo-choices", "data"),
    ],
    background=True,
)
def files_per_commit(repolist):
    """Queries Augur for the number of files per commit for repos in repolist
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
            avg(f.num_files) as avg_files
        from
            (select
                /*commit_hash'es are unique per commit*/
                count(*) as num_files
            from
                commits c,
                repo r
            where
                r.repo_id in ({str(repolist)[1:-1]})
                and c.repo_id = r.repo_id
            group by c.cmt_commit_hash) as f
        """
    )

    return round(df.iat[0, 0], 2)
