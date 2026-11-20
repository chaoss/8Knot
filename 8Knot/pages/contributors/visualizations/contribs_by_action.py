from dash import dcc, callback
import dash
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import pandas as pd
import logging
from dateutil.relativedelta import *  # type: ignore
import plotly.express as px
from pages.utils.graph_utils import get_graph_time_values, baby_blue
from queries.contributors_query import contributors_query as ctq
from pages.utils.job_utils import nodata_graph, POLL_INTERVAL_MS
import time
import app
import pages.utils.preprocessing_utils as preproc_utils
import cache_manager.cache_facade as cf

from components.visualization import VisualizationAIO

PAGE = "contributors"
VIZ_ID = "contribs-by-action"

gc_contribs_by_action = VisualizationAIO(
    PAGE,
    VIZ_ID,
    title="Contributors by Action Type",
    graph_info="""
    Visualizes the number of contributors who have performed a specific action\n
    (have opened a PR, for example) within a specified time-window. This is different\n
    from counting the number of contributions (the number of PRs having been opened)-\n
    the focus is on the activity of distinct contributors.
    """,
    controls=[
        dbc.Row(
            [
                dbc.Label(
                    "Action Type:",
                    html_for=f"action-dropdown-{PAGE}-{VIZ_ID}",
                    width={"size": "auto"},
                ),
                dbc.Col(
                    [
                        dcc.Dropdown(
                            id=f"action-dropdown-{PAGE}-{VIZ_ID}",
                            options=[
                                {
                                    "label": "PR Open",
                                    "value": "PR Opened",
                                },
                                {
                                    "label": "Comment",
                                    "value": "Comment",
                                },
                                {
                                    "label": "PR Review",
                                    "value": "PR Review",
                                },
                                {
                                    "label": "Issue Opened",
                                    "value": "Issue Opened",
                                },
                                {
                                    "label": "Issue Closed",
                                    "value": "Issue Closed",
                                },
                                {"label": "Commit", "value": "Commit"},
                            ],
                            value="PR Opened",
                            clearable=False,
                            className="dark-dropdown",
                        ),
                        dbc.Alert(
                            children="""No contributions of this type have been made.\n
                            Please select a different contribution type.""",
                            id=f"check-alert-{PAGE}-{VIZ_ID}",
                            dismissable=True,
                            fade=False,
                            is_open=False,
                            color="warning",
                        ),
                    ],
                    className="me-2",
                    width=3,
                ),
            ],
            align="center",
        ),
        dbc.Row(
            [
                dbc.Label(
                    "Date Interval:",
                    html_for=f"date-interval-{PAGE}-{VIZ_ID}",
                    width="auto",
                ),
                dbc.Col(
                    dbc.RadioItems(
                        id=f"date-interval-{PAGE}-{VIZ_ID}",
                        options=[
                            {"label": "Month", "value": "M1"},
                            {"label": "Quarter", "value": "M3"},
                            {"label": "6 Months", "value": "M6"},
                            {"label": "Year", "value": "M12"},
                        ],
                        value="M1",
                        inline=True,
                        className="custom-radio-buttons",
                    ),
                ),
            ],
            align="center",
        ),
    ],
    class_name="dark-card",
    id="contributor-actions",
)


# callback for contributors by action graph
@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    Output(f"check-alert-{PAGE}-{VIZ_ID}", "is_open"),
    [
        Input("repo-choices", "data"),
        Input(f"date-interval-{PAGE}-{VIZ_ID}", "value"),
        Input(f"action-dropdown-{PAGE}-{VIZ_ID}", "value"),
        Input("bot-switch", "value"),
    ],
    background=True,
    interval=POLL_INTERVAL_MS,
)
def contribs_by_action_graph(repolist, interval, action, bot_switch):
    # wait for data to asynchronously download and become available.
    while not_cached := cf.get_uncached(func_name=ctq.__name__, repolist=repolist):
        logging.warning(f"{VIZ_ID}- WAITING ON DATA TO BECOME AVAILABLE")
        time.sleep(0.5)

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
        return nodata_graph, False

    # remove bot data
    if bot_switch:
        df = df[~df["cntrb_id"].isin(app.bots_list)]

    # checks if there is a contribution of a specfic action in repo set
    if not df["Action"].str.contains(action).any():
        return dash.no_update, True

    # function for all data pre processing
    df = process_data(df, interval, action)

    fig = create_figure(df, interval, action)

    logging.warning(f"{VIZ_ID} - END - {time.perf_counter() - start}")
    return fig, False


def process_data(df: pd.DataFrame, interval, action):
    # convert to datetime objects rather than strings
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)

    # order values chronologically by COLUMN_TO_SORT_BY date
    df = df.sort_values(by="created_at", axis=0, ascending=True)

    # drop all contributions that are not the selected action
    df = df[df["Action"].str.contains(action)]

    # For distinct contributors per interval: keep one row per (cntrb_id, interval)
    """df["_period"] = df["created_at"].dt.to_period(interval)
    df = df.drop_duplicates(subset=["cntrb_id", "_period"], keep="first")
    # Use the start of the interval for plotting consistency
    df["created_at"] = df["_period"].dt.start_time
    df = df.drop(columns=["_period"])  # cleanup"""

    freq_map = {"M1": "M", "M3": "Q", "M6": "2Q", "M12": "Y"}
    pandas_freq = freq_map.get(interval, interval)

    df["_period"] = df["created_at"].dt.to_period(pandas_freq)
    df = df.drop_duplicates(subset=["cntrb_id", "_period"], keep="first")
    df["created_at"] = df["_period"].dt.start_time
    df = df.drop(columns=["_period"])
    print(df)

    return df


def create_figure(df: pd.DataFrame, interval, action):
    # time values for graph
    x_r, x_name, hover, period = get_graph_time_values(interval)

    # create plotly express histogram
    fig = px.histogram(df, x="created_at", color_discrete_sequence=[baby_blue[3]])

    # creates bins with interval size and customizes the hover value for the bars
    fig.update_traces(
        xbins_size=interval,
        hovertemplate=hover + "<br>" + action + " Contributors: %{y}<br><extra></extra>",
        marker_line_width=0.1,
        marker_line_color="black",
    )

    # update xaxes to align for the interval bin size
    fig.update_xaxes(
        showgrid=True,
        ticklabelmode="period",
        dtick=period,
        rangeslider_yaxis_rangemode="match",
        range=x_r,
    )

    # layout styling
    fig.update_layout(
        xaxis_title=x_name,
        yaxis_title="Contributors",
        margin_b=40,
        font=dict(size=14),
    )

    return fig
