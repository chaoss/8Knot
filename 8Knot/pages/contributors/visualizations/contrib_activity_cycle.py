from dash import callback
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import pandas as pd
import logging
from dateutil.relativedelta import *  # type: ignore
import plotly.express as px
from pages.utils.graph_utils import baby_blue
from queries.commits_query import commits_query as cmq
import cache_manager.cache_facade as cf
from pages.utils.job_utils import nodata_graph, POLL_INTERVAL_MS
import time
from components.visualization import VisualizationAIO

PAGE = "contributors"
VIZ_ID = "contrib-activity-cycle"


gc_contrib_activity_cycle = VisualizationAIO(
    PAGE,
    VIZ_ID,
    title="Contributor Activity Cycle",
    graph_info="""
    Visualizes the distribution of Commit timestamps by Weekday or Hour.\n
    Helps to describe operating-hours of community code contributions.
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
                        "label": "Weekday",
                        "value": "D",
                    },
                    {"label": "Hourly", "value": "H"},
                ],
                value="D",
                inline=True,
                className="custom-radio-buttons",
            ),
            className="me-2",
            width=4,
        ),
    ],
    class_name="dark-card",
    id="contributor-activity-cycle",
)


# callback for VIZ TITLE graph
@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    [
        Input("repo-choices", "data"),
        Input(f"date-interval-{PAGE}-{VIZ_ID}", "value"),
    ],
    background=True,
    interval=POLL_INTERVAL_MS,
)
def contrib_activity_cycle_graph(repolist, interval):
    # wait for data to asynchronously download and become available.
    while not_cached := cf.get_uncached(func_name=cmq.__name__, repolist=repolist):
        logging.warning(f"COMMITS_OVER_TIME_VIZ - WAITING ON DATA TO BECOME AVAILABLE")
        time.sleep(0.5)

    start = time.perf_counter()
    logging.warning(f"{VIZ_ID}- START")

    # GET ALL DATA FROM POSTGRES CACHE
    df = cf.retrieve_from_cache(
        tablename=cmq.__name__,
        repolist=repolist,
    )

    # test if there is data
    if df.empty:
        logging.warning(f"{VIZ_ID} - NO DATA AVAILABLE")
        return nodata_graph

    # function for all data pre processing, COULD HAVE ADDITIONAL INPUTS AND OUTPUTS
    df = process_data(df, interval)

    fig = create_figure(df, interval)

    logging.warning(f"{VIZ_ID} - END - {time.perf_counter() - start}")
    return fig


def process_data(df: pd.DataFrame, interval):
    # for this usecase we want the datetimes to be in their local values
    # tricking pandas to keep local values when UTC conversion is required for to_datetime
    df["author_timestamp"] = df["author_timestamp"].astype("str").str[:-6]
    df["committer_timestamp"] = df["committer_timestamp"].astype("str").str[:-6]

    # convert to datetime objects rather than strings
    df["author_timestamp"] = pd.to_datetime(df["author_timestamp"], utc=True)
    df["committer_timestamp"] = pd.to_datetime(df["committer_timestamp"], utc=True)
    # removes duplicate values when the author and committer is the same
    df.loc[df["author_timestamp"] == df["committer_timestamp"], "author_timestamp"] = None

    df_final = pd.DataFrame()

    if interval == "H":
        # combine the hour values for author and committer
        hour = pd.concat([df["author_timestamp"].dt.hour, df["committer_timestamp"].dt.hour])
        df_hour = pd.DataFrame(hour, columns=["Hour"])
        df_final = df_hour.groupby(["Hour"])["Hour"].count()
    else:
        # combine the weekday values for author and committer
        weekday = pd.concat(
            [
                df["author_timestamp"].dt.day_name(),
                df["committer_timestamp"].dt.day_name(),
            ]
        )
        df_weekday = pd.DataFrame(weekday, columns=["Weekday"])
        df_final = df_weekday.groupby(["Weekday"])["Weekday"].count()

    return df_final


def create_figure(df: pd.DataFrame, interval):
    column = "Weekday"
    order = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    if interval == "H":
        column = "Hour"

    fig = px.bar(df, y=column, color_discrete_sequence=[baby_blue[3]])
    hover = "%{x} Activity Count: %{y}<br>"
    if interval == "H":
        hover = "Hour: %{x}:00 Activity Count: %{y}<br>"
    fig.update_traces(hovertemplate=hover)
    fig.update_xaxes(
        categoryorder="array",
        categoryarray=order,
    )
    fig.update_layout(
        yaxis_title="Activity Count",
        xaxis_title=column,
        font=dict(size=14),
    )

    return fig
