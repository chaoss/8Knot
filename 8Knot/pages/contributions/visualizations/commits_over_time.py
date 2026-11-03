import dash_bootstrap_components as dbc
from dash import callback
from dash.dependencies import Input, Output
import pandas as pd
import logging
import plotly.express as px
from pages.utils.graph_utils import get_graph_time_values, baby_blue
from queries.commits_query import commits_query as cmq
from pages.utils.job_utils import nodata_graph
import time
import cache_manager.cache_facade as cf
from components.visualization import VisualizationAIO

PAGE = "contributions"
VIZ_ID = "commits-over-time"

gc_commits_over_time = VisualizationAIO(
    PAGE,
    VIZ_ID,
    title="Commits Over Time",
    graph_info="""
    Visualizes the number of commits added to the project.\n
    Commits are counted relative to a user-selected time window.
    """,
    controls=[
        dbc.Label(
            "Date Interval:",
            html_for=f"date-interval-{PAGE}-{VIZ_ID}",
            width={"size": "auto"},
        ),
        dbc.Col(
            dbc.RadioItems(
                id=f"date-interval-{PAGE}-{VIZ_ID}",
                options=[
                    {
                        "label": "Day",
                        "value": "D",
                    },
                    {
                        "label": "Week",
                        "value": "W",
                    },
                    {"label": "Month", "value": "M"},
                    {"label": "Year", "value": "Y"},
                ],
                value="M",
                inline=True,
                className="custom-radio-buttons",
            ),
            className="me-2",
            width=4,
        ),
    ],
    class_name="dark-card",
    id="commits-over-time",
)


# callback for commits over time graph
@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    [
        Input("repo-choices", "data"),
        Input(f"date-interval-{PAGE}-{VIZ_ID}", "value"),
    ],
    background=True,
)
def commits_over_time_graph(repolist, interval):
    # wait for data to asynchronously download and become available.
    cf.wait_for_cache(func_name=cmq.__name__, repolist=repolist)

    # data ready.
    start = time.perf_counter()
    logging.warning("COMMITS_OVER_TIME_VIZ - START")

    # GET ALL DATA FROM POSTGRES CACHE
    df = cf.retrieve_from_cache(
        tablename=cmq.__name__,
        repolist=repolist,
    )

    # test if there is data
    if df.empty:
        logging.warning("COMMITS OVER TIME - NO DATA AVAILABLE")
        return nodata_graph

    # function for all data pre processing
    df_created = process_data(df, interval)

    fig = create_figure(df_created, interval)

    logging.warning(f"COMMITS_OVER_TIME_VIZ - END - {time.perf_counter() - start}")
    return fig


def process_data(df: pd.DataFrame, interval):
    # convert to datetime objects with consistent column name
    # incoming value should be a posix integer.
    df["author_date"] = pd.to_datetime(df["author_date"], utc=True)
    df.rename(columns={"author_date": "created_at"}, inplace=True)

    # variable to slice on to handle weekly period edge case
    period_slice = None
    if interval == "W":
        # this is to slice the extra period information that comes with the weekly case
        period_slice = 10

    # get the count of commits in the desired interval in pandas period format, sort index to order entries
    df_created = (
        df.groupby(by=df.created_at.dt.to_period(interval))["commit_hash"]
        .nunique()
        .reset_index()
        .rename(columns={"created_at": "Date"})
    )

    # converts date column to a datetime object, converts to string first to handle period information
    # the period slice is to handle weekly corner case
    df_created["Date"] = pd.to_datetime(df_created["Date"].astype(str).str[:period_slice])

    return df_created


def create_figure(df_created: pd.DataFrame, interval):
    # time values for graph
    x_r, x_name, hover, period = get_graph_time_values(interval)

    # graph geration
    fig = px.bar(
        df_created,
        x="Date",
        y="commit_hash",
        range_x=x_r,
        labels={"x": x_name, "y": "Commits"},
        color_discrete_sequence=[baby_blue[3]],
    )
    fig.update_traces(hovertemplate=hover + "<br>Commits: %{y}<br>")
    fig.update_xaxes(
        showgrid=True,
        ticklabelmode="period",
        dtick=period,
        rangeslider_yaxis_rangemode="match",
        range=x_r,
    )
    fig.update_layout(
        xaxis_title=x_name,
        yaxis_title="Number of Commits",
        margin_b=40,
        margin_r=20,
        font=dict(size=14),
    )

    return fig
