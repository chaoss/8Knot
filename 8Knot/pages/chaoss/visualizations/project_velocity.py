from dash import html, dcc, callback
import dash
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import pandas as pd
import logging
from dateutil.relativedelta import *  # type: ignore
import plotly.express as px
from pages.utils.graph_utils import get_graph_time_values, baby_blue
from queries.contributors_query import contributors_query as ctq
from pages.utils.job_utils import nodata_graph
import time
import datetime as dt
import math
import numpy as np
import app
import pages.utils.preprocessing_utils as preproc_utils
import cache_manager.cache_facade as cf
from components.visualization import VisualizationAIO

PAGE = "chaoss"
VIZ_ID = "project-velocity"

gc_project_velocity = VisualizationAIO(
    PAGE,
    VIZ_ID,
    title="Project Velocity",
    graph_info="""
        This visualization gives a view into the development speed of a repository in\n
        relation to the other selected repositories. For more context of this visualization see\n
        https://chaoss.community/kb/metric-project-velocity/ \n
        https://www.cncf.io/blog/2017/06/05/30-highest-velocity-open-source-projects/
    """,
    controls=[
        html.Div(
            [
                dbc.Label(
                    [
                        "Issue Opened Weight:",
                        dbc.Input(
                            id=f"issue-opened-weight-{PAGE}-{VIZ_ID}",
                            type="number",
                            min=0,
                            max=1,
                            step=0.1,
                            value=0.3,
                            size="sm",
                            style={"width": "80px"},
                            className="dark-input ms-4",
                        ),
                    ],
                    className="d-flex align-items-baseline me-5 mb-3",
                ),
                dbc.Label(
                    [
                        "Issue Closed Weight:",
                        dbc.Input(
                            id=f"issue-closed-weight-{PAGE}-{VIZ_ID}",
                            type="number",
                            min=0,
                            max=1,
                            step=0.1,
                            value=0.4,
                            size="sm",
                            style={"width": "80px"},
                            className="dark-input ms-4",
                        ),
                    ],
                    className="d-flex align-items-baseline me-5 mb-3",
                ),
                dbc.Label(
                    [
                        "PR Open Weight:",
                        dbc.Input(
                            id=f"pr-open-weight-{PAGE}-{VIZ_ID}",
                            type="number",
                            min=0,
                            max=1,
                            step=0.1,
                            value=0.5,
                            size="sm",
                            style={"width": "80px"},
                            className="dark-input ms-4",
                        ),
                    ],
                    className="d-flex align-items-baseline me-5 mb-3",
                ),
                dbc.Label(
                    [
                        "PR Merged Weight:",
                        dbc.Input(
                            id=f"pr-merged-weight-{PAGE}-{VIZ_ID}",
                            type="number",
                            min=0,
                            max=1,
                            step=0.1,
                            value=0.7,
                            size="sm",
                            style={"width": "80px"},
                            className="dark-input ms-4",
                        ),
                    ],
                    className="d-flex align-items-baseline me-5 mb-3",
                ),
                dbc.Label(
                    [
                        "PR Closed Weight:",
                        dbc.Input(
                            id=f"pr-closed-weight-{PAGE}-{VIZ_ID}",
                            type="number",
                            min=0,
                            max=1,
                            step=0.1,
                            value=0.2,
                            size="sm",
                            style={"width": "80px"},
                            className="dark-input ms-4",
                        ),
                    ],
                    className="d-flex align-items-baseline me-5 mb-3",
                ),
                dbc.Label(
                    [
                        "Y-axis:",
                        dbc.RadioItems(
                            id=f"graph-view-{PAGE}-{VIZ_ID}",
                            options=[
                                {"label": "Non-log", "value": False},
                                {"label": "Log", "value": True},
                            ],
                            value=False,
                            inline=True,
                            className="custom-radio-buttons ms-4",
                        ),
                    ],
                    className="d-flex align-items-baseline me-5 mb-3",
                ),
                dcc.DatePickerRange(
                    id=f"date-picker-range-{PAGE}-{VIZ_ID}",
                    min_date_allowed=dt.date(2005, 1, 1),
                    max_date_allowed=dt.date.today(),
                    initial_visible_month=dt.date(dt.date.today().year, 1, 1),
                    clearable=True,
                    className="dark-date-picker mb-3",
                ),
            ],
            className="d-flex flex-wrap align-items-center",
            style={"gap": "1rem"},
        )
    ],
    class_name="dark-card",
    id="project-velocity",
)


# callback for Project Velocity graph
@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    [
        Input("repo-choices", "data"),
        Input(f"graph-view-{PAGE}-{VIZ_ID}", "value"),
        Input(f"issue-opened-weight-{PAGE}-{VIZ_ID}", "value"),
        Input(f"issue-closed-weight-{PAGE}-{VIZ_ID}", "value"),
        Input(f"pr-open-weight-{PAGE}-{VIZ_ID}", "value"),
        Input(f"pr-merged-weight-{PAGE}-{VIZ_ID}", "value"),
        Input(f"pr-closed-weight-{PAGE}-{VIZ_ID}", "value"),
        Input(f"date-picker-range-{PAGE}-{VIZ_ID}", "start_date"),
        Input(f"date-picker-range-{PAGE}-{VIZ_ID}", "end_date"),
        Input("bot-switch", "value"),
    ],
    background=True,
)
def project_velocity_graph(
    repolist,
    log,
    i_o_weight,
    i_c_weight,
    pr_o_weight,
    pr_m_weight,
    pr_c_weight,
    start_date,
    end_date,
    bot_switch,
):
    # wait for data to asynchronously download and become available.
    cf.wait_for_cache(func_name=ctq.__name__, repolist=repolist)

    logging.warning(f"{VIZ_ID} - START")
    start = time.perf_counter()

    # GET ALL DATA FROM POSTGRES CACHE
    df = cf.retrieve_from_cache(
        tablename=ctq.__name__,
        repolist=repolist,
    )

    df = preproc_utils.contributors_df_action_naming(df)

    # test if there is data
    if df.empty:
        logging.warning(f"{VIZ_ID} - NO DATA AVAILABLE")
        return nodata_graph

    # remove bot data
    if bot_switch:
        df = df[~df["cntrb_id"].isin(app.bots_list)]

    # function for all data pre processing
    df = process_data(
        df,
        start_date,
        end_date,
        i_o_weight,
        i_c_weight,
        pr_o_weight,
        pr_m_weight,
        pr_c_weight,
    )

    fig = create_figure(df, log)

    logging.warning(f"{VIZ_ID} - END - {time.perf_counter() - start}")
    return fig


def process_data(
    df: pd.DataFrame,
    start_date,
    end_date,
    i_o_weight,
    i_c_weight,
    pr_o_weight,
    pr_m_weight,
    pr_c_weight,
):
    # convert to datetime objects rather than strings
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)

    # order values chronologically by COLUMN_TO_SORT_BY date
    df = df.sort_values(by="created_at", axis=0, ascending=True)

    # filter values based on date picker
    if start_date is not None:
        df = df[df.created_at >= start_date]
    if end_date is not None:
        df = df[df.created_at <= end_date]

    # df to hold value of unique contributors for each repo
    df_cntrbs = pd.DataFrame(df.groupby("repo_name")["cntrb_id"].nunique()).rename(
        columns={"cntrb_id": "num_unique_contributors"}
    )

    # group actions and repos to get the counts of the actions by repo
    df_actions = pd.DataFrame(df.groupby("repo_name")["Action"].value_counts())
    df_actions = df_actions.rename(columns={"Action": "count"}).reset_index()

    # pivot df to reformat the actions to be columns and repo_id to be rows
    df_actions = df_actions.pivot(index="repo_name", columns="Action", values="count")

    # df_consolidated combines the actions and unique contributors and then specific columns for visualization use are added on
    df_consolidated = pd.concat([df_actions, df_cntrbs], axis=1).reset_index()

    # replace all nan to 0
    df_consolidated.fillna(value=0, inplace=True)

    # log of pr_open and contribs if values are not 0
    df_consolidated["log_num_pr_open"] = df_consolidated["PR Opened"].apply(lambda x: math.log(x) if x != 0 else 0)
    df_consolidated["log_num_contrib"] = df_consolidated["num_unique_contributors"].apply(
        lambda x: math.log(x) if x != 0 else 0
    )

    # column to hold the weighted values of pr and issues actions summed together
    df_consolidated["prs_issues_actions_weighted"] = (
        df_consolidated["Issue Opened"] * i_o_weight
        + df_consolidated["Issue Closed"] * i_c_weight
        + df_consolidated["PR Opened"] * pr_o_weight
        + df_consolidated["PR Merged"] * pr_m_weight
        + df_consolidated["PR Closed"] * pr_c_weight
    )

    # after weighting replace 0 with nan for log
    df_consolidated["prs_issues_actions_weighted"].replace(0, np.nan, inplace=True)

    # column for log value of pr and issue actions
    df_consolidated["log_prs_issues_actions_weighted"] = df_consolidated["prs_issues_actions_weighted"].apply(math.log)

    return df_consolidated


def create_figure(df: pd.DataFrame, log):
    y_axis = "prs_issues_actions_weighted"
    y_title = "Weighted PR/Issue Actions"
    if log:
        y_axis = "log_prs_issues_actions_weighted"
        y_title = "Log of Weighted PR/Issue Actions"

    # graph generation
    fig = px.scatter(
        df,
        x="log_num_pr_open",
        y=y_axis,
        color="repo_name",
        size="log_num_contrib",
        hover_data=[
            "repo_name",
            "PR Opened",
            "Issue Opened",
            "num_unique_contributors",
        ],
        color_discrete_sequence=baby_blue,
    )

    fig.update_traces(
        hovertemplate="Repo: %{customdata[0]}  <br>Total PRs: %{customdata[2]} <br>Total Issues: %{customdata[3]} "
        + "<br>Total Contributors: %{customdata[4]}<br><extra></extra>",
    )

    # layout styling
    fig.update_layout(
        xaxis_title="Logarithmic PRs Opened",
        yaxis_title=y_title,
        margin_b=40,
        font=dict(size=14),
        legend_title="Repo Name",
    )

    return fig
