from dash import callback
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import plotly.graph_objects as go
import pandas as pd
import logging
from dateutil.relativedelta import *  # type: ignore
import plotly.express as px
from pages.utils.graph_utils import get_graph_time_values, baby_blue
from queries.pr_assignee_query import pr_assignee_query as praq
from pages.utils.job_utils import nodata_graph
from pages.utils.pr_assignment_utils import pr_assignment
import time
import app
import cache_manager.cache_facade as cf
from components.visualization import VisualizationAIO

PAGE = "contributions"
VIZ_ID = "pr_assignment"

gc_pr_assignment = VisualizationAIO(
    PAGE,
    VIZ_ID,
    title="Pull Request Review Status Counts",
    graph_info="""
    Visualizes the number of assigned and unassigned pull requests in each \n
    time bucket.
    """,
    controls=[
        dbc.Label(
            "Date Interval:",
            html_for=f"date-radio-{PAGE}-{VIZ_ID}",
            width={"size": "auto"},
        ),
        dbc.Col(
            dbc.RadioItems(
                id=f"date-radio-{PAGE}-{VIZ_ID}",
                options=[
                    {"label": "Trend", "value": "D"},
                    {"label": "Week", "value": "W"},
                    {"label": "Month", "value": "M"},
                    {"label": "Year", "value": "Y"},
                ],
                value="W",
                inline=True,
                className="custom-radio-buttons",
            ),
            className="me-2",
            width=4,
        ),
    ],
    class_name="dark-card",
    id="pr_assignment",
)


# callback for pull request review assignment graph
@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    [
        Input("repo-choices", "data"),
        Input(f"date-radio-{PAGE}-{VIZ_ID}", "value"),
        Input("bot-switch", "value"),
    ],
    background=True,
)
def pr_assignment_graph(repolist, interval, bot_switch):
    # wait for data to asynchronously download and become available.
    while not_cached := cf.get_uncached(func_name=praq.__name__, repolist=repolist):
        logging.warning(f"{VIZ_ID} - WAITING ON DATA TO BECOME AVAILABLE")
        time.sleep(0.5)

    # data ready.
    start = time.perf_counter()
    logging.warning(f"{VIZ_ID}- START")

    # GET ALL DATA FROM POSTGRES CACHE
    df = cf.retrieve_from_cache(
        tablename=praq.__name__,
        repolist=repolist,
    )

    start = time.perf_counter()
    logging.warning(f"{VIZ_ID}- START")

    # test if there is data
    if df.empty:
        logging.warning(f"{VIZ_ID} - NO DATA AVAILABLE")
        return nodata_graph

    # remove assignment data if assigned to a bot
    if bot_switch:
        df["bot"] = df["assignee"].isin(app.bots_list)
        df.loc[df.bot == True, "assign_date"] = None
        df.loc[df.bot == True, "assignment_action"] = None
        df.loc[df.bot == True, "assignee"] = None

    df = process_data(df, interval)

    fig = create_figure(df, interval)

    logging.warning(f"{VIZ_ID} - END - {time.perf_counter() - start}")
    return fig


def process_data(df: pd.DataFrame, interval):
    # convert to datetime objects rather than strings
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    df["closed_at"] = pd.to_datetime(df["closed_at"], utc=True)
    df["assign_date"] = pd.to_datetime(df["assign_date"], utc=True)

    # order values chronologically by created date
    df = df.sort_values(by="created_at", axis=0, ascending=True)

    # first and last elements of the dataframe are the
    # earliest and latest events respectively
    earliest = df["created_at"].min()
    latest = max(df["created_at"].max(), df["closed_at"].max())

    # generating buckets beginning to the end of time by the specified interval
    dates = pd.date_range(start=earliest, end=latest, freq=interval, inclusive="both")

    # df for pr review assignments in date intervals
    df_assign = dates.to_frame(index=False, name="start_date")

    # offset end date column by interval
    if interval == "D":
        df_assign["end_date"] = df_assign.start_date + pd.DateOffset(days=1)
    elif interval == "W":
        df_assign["end_date"] = df_assign.start_date + pd.DateOffset(weeks=1)
    elif interval == "M":
        df_assign["end_date"] = df_assign.start_date + pd.DateOffset(months=1)
    else:
        df_assign["end_date"] = df_assign.start_date + pd.DateOffset(years=1)

    # dynamically apply the function to all dates defined in the date_range to create df_status
    df_assign["Assigned"], df_assign["Unassigned"] = zip(
        *df_assign.apply(
            lambda row: pr_assignment(df, row.start_date, row.end_date),
            axis=1,
        )
    )

    # formatting for graph generation
    if interval == "M":
        df_assign["start_date"] = df_assign["start_date"].dt.strftime("%Y-%m")
    elif interval == "Y":
        df_assign["start_date"] = df_assign["start_date"].dt.year

    return df_assign


def create_figure(df: pd.DataFrame, interval):
    # time values for graph
    x_r, x_name, hover, period = get_graph_time_values(interval)

    # making a line graph if the bin-size is small enough.
    if interval == "D":
        fig = go.Figure(
            [
                go.Scatter(
                    name="Assigned",
                    x=df["start_date"],
                    y=df["Assigned"],
                    mode="lines",
                    showlegend=True,
                    hovertemplate="PRs Assigned: %{y}<br>%{x|%b %d, %Y} <extra></extra>",
                    marker=dict(color=baby_blue[8]),
                ),
                go.Scatter(
                    name="Unassigned",
                    x=df["start_date"],
                    y=df["Unassigned"],
                    mode="lines",
                    showlegend=True,
                    hovertemplate="PRs Unassigned: %{y}<br>%{x|%b %d, %Y}<extra></extra>",
                    marker=dict(color=baby_blue[6]),
                ),
            ]
        )
    else:
        fig = px.bar(
            df,
            x="start_date",
            y=["Assigned", "Unassigned"],
            color_discrete_sequence=[baby_blue[8], baby_blue[6]],
        )

        # edit hover values
        fig.update_traces(hovertemplate=hover + "<br>PRs: %{y}<br><extra></extra>")

        fig.update_xaxes(
            showgrid=True,
            ticklabelmode="period",
            dtick=period,
            rangeslider_yaxis_rangemode="match",
            range=x_r,
        )

    # layout specifics for both styles of plots
    fig.update_layout(
        xaxis_title="Time",
        yaxis_title="Pull Requests",
        legend_title="Types",
        font=dict(size=14),
    )

    return fig
