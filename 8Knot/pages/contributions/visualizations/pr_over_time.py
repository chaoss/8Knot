import dash_bootstrap_components as dbc
from dash import callback
from dash.dependencies import Input, Output
import plotly.graph_objects as go
import pandas as pd
import logging
from pages.utils.graph_utils import get_graph_time_values, baby_blue
from pages.utils.job_utils import nodata_graph
from queries.prs_query import prs_query as prq
import time
import cache_manager.cache_facade as cf
from components.visualization import VisualizationAIO

PAGE = "contributions"
VIZ_ID = "prs-over-time"

gc_pr_over_time = VisualizationAIO(
    PAGE,
    VIZ_ID,
    title="Pull Requests Over Time",
    graph_info="""
    Visualizes PR behavior by tracking Created, Merged, and Closed-Not-Merged PRs over time.\n
    Also shows Created PR count as a trend over lifespan.
    """,
    controls=[
        dbc.Label(
            "Date Interval:",
            html_for=f"date-interval-{PAGE}-{VIZ_ID}",
            width="auto",
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
    id="prs-over-time",
)


# callback for prs over time graph
@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    [
        Input("repo-choices", "data"),
        Input(f"date-interval-{PAGE}-{VIZ_ID}", "value"),
    ],
    background=True,
)
def prs_over_time_graph(repolist, interval):
    # wait for data to asynchronously download and become available.
    cf.wait_for_cache(func_name=prq.__name__, repolist=repolist)

    # data ready.
    start = time.perf_counter()
    logging.warning("PULL REQUESTS OVER TIME - START")

    # GET ALL DATA FROM POSTGRES CACHE
    df = cf.retrieve_from_cache(
        tablename=prq.__name__,
        repolist=repolist,
    )

    # test if there is data
    if df.empty:
        logging.warning("PULL REQUESTS OVER TIME - NO DATA AVAILABLE")
        return nodata_graph

    # function for all data pre processing
    df_created, df_closed_merged, df_open = process_data(df, interval)

    fig = create_figure(df_created, df_closed_merged, df_open, interval)

    logging.warning(f"PRS_OVER_TIME_VIZ - END - {time.perf_counter() - start}")

    return fig


def process_data(df: pd.DataFrame, interval):
    # convert dates to datetime objects rather than strings
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    df["merged_at"] = pd.to_datetime(df["merged_at"], utc=True)
    df["closed_at"] = pd.to_datetime(df["closed_at"], utc=True)

    # order values chronologically by creation date
    df = df.sort_values(by="created_at", axis=0, ascending=True)

    # variable to slice on to handle weekly period edge case
    period_slice = None
    if interval == "W":
        # this is to slice the extra period information that comes with the weekly case
        period_slice = 10

    # --data frames for PR created, merged, or closed. Detailed description applies for all 3.--

    # get the count of created prs in the desired interval in pandas period format, sort index to order entries
    created_range = df["created_at"].dt.to_period(interval).value_counts().sort_index()

    # converts to data frame object and created date column from period values
    df_created = created_range.to_frame().reset_index().rename(columns={"created_at": "Date", "count": "created_at"})

    # converts date column to a datetime object, converts to string first to handle period information
    # the period slice is to handle weekly corner case
    df_created["Date"] = pd.to_datetime(df_created["Date"].astype(str).str[:period_slice])

    # df for merged prs in time interval
    merged_range = pd.to_datetime(df["merged_at"]).dt.to_period(interval).value_counts().sort_index()
    df_merged = merged_range.to_frame().reset_index().rename(columns={"merged_at": "Date", "count": "merged_at"})
    df_merged["Date"] = pd.to_datetime(df_merged["Date"].astype(str).str[:period_slice])

    # df for closed prs in time interval
    closed_range = pd.to_datetime(df["closed_at"]).dt.to_period(interval).value_counts().sort_index()
    df_closed = closed_range.to_frame().reset_index().rename(columns={"closed_at": "Date", "count": "closed_at"})
    df_closed["Date"] = pd.to_datetime(df_closed["Date"].astype(str).str[:period_slice])

    # A single df created for plotting merged and closed as stacked bar chart
    df_closed_merged = pd.merge(df_merged, df_closed, on="Date", how="outer")

    # formatting for graph generation
    if interval == "M":
        df_created["Date"] = df_created["Date"].dt.strftime("%Y-%m-01")
        df_closed_merged["Date"] = df_closed_merged["Date"].dt.strftime("%Y-%m-01")
    elif interval == "Y":
        df_created["Date"] = df_created["Date"].dt.strftime("%Y-01-01")
        df_closed_merged["Date"] = df_closed_merged["Date"].dt.strftime("%Y-01-01")

    df_closed_merged["closed_at"] = df_closed_merged["closed_at"] - df_closed_merged["merged_at"]

    # ----- Open PR processinging starts here ----

    # first and last elements of the dataframe are the
    # earliest and latest events respectively
    earliest = df["created_at"].min()
    latest = max(df["created_at"].max(), df["closed_at"].max())

    # beginning to the end of time by the specified interval
    dates = pd.date_range(start=earliest, end=latest, freq="D", inclusive="both")

    # df for open prs from time interval
    df_open = dates.to_frame(index=False, name="Date")

    # aplies function to get the amount of open prs for each day
    df_open["Open"] = df_open.apply(lambda row: get_open(df, row.Date), axis=1)

    df_open["Date"] = df_open["Date"].dt.strftime("%Y-%m-%d")

    return df_created, df_closed_merged, df_open


def create_figure(
    df_created: pd.DataFrame,
    df_closed_merged: pd.DataFrame,
    df_open: pd.DataFrame,
    interval,
):
    # time values for graph
    x_r, x_name, hover, period = get_graph_time_values(interval)

    # graph generation
    fig = go.Figure()
    fig.add_bar(
        x=df_created["Date"],
        y=df_created["created_at"],
        opacity=0.9,
        hovertemplate=hover + "<br>Created: %{y}<br>" + "<extra></extra>",
        offsetgroup=0,
        marker=dict(color=baby_blue[6]),
        name="Opened",
    )
    fig.add_bar(
        x=df_closed_merged["Date"],
        y=df_closed_merged["merged_at"],
        opacity=0.9,
        hovertemplate=hover + "<br>Merged: %{y}<br>" + "<extra></extra>",
        offsetgroup=1,
        marker=dict(color=baby_blue[0]),
        name="Merged",
    )
    fig.add_bar(
        x=df_closed_merged["Date"],
        y=df_closed_merged["closed_at"],
        opacity=0.9,
        hovertemplate=[f"{hover}<br>Closed: {val}<br><extra></extra>" for val in df_closed_merged["closed_at"]],
        offsetgroup=1,
        base=df_closed_merged["merged_at"],
        marker=dict(color=baby_blue[2]),
        name="Closed",
    )
    fig.update_xaxes(
        showgrid=True,
        ticklabelmode="period",
        dtick=period,
        rangeslider_yaxis_rangemode="match",
        range=x_r,
    )
    fig.update_layout(
        xaxis_title=x_name,
        yaxis_title="Number of PRs",
        bargroupgap=0.1,
        margin_b=40,
        font=dict(size=14),
    )
    fig.add_trace(
        go.Scatter(
            x=df_open["Date"],
            y=df_open["Open"],
            mode="lines",
            marker=dict(color=baby_blue[8]),
            name="Open",
            hovertemplate="PRs Open: %{y}<br>%{x|%b %d, %Y} <extra></extra>",
        )
    )

    return fig


# for each day, this function calculates the amount of open prs
def get_open(df, date):
    # drop rows that are more recent than the date limit
    df_created = df[df["created_at"] <= date]

    # drops rows that have been closed after date
    df_open = df_created[df_created["closed_at"] > date]

    # include prs that have not been close yet
    df_open = pd.concat([df_open, df_created[df_created.closed_at.isnull()]])

    # generates number of columns ie open prs
    num_open = df_open.shape[0]
    return num_open
