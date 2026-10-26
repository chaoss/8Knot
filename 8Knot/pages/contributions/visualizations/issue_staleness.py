import dash
import dash_bootstrap_components as dbc
from dash import callback
from dash.dependencies import Input, Output
import plotly.graph_objects as go
import pandas as pd
import logging
from dateutil.relativedelta import *  # type: ignore
import plotly.express as px
from pages.utils.graph_utils import get_graph_time_values, baby_blue
from queries.issues_query import issues_query as iq
from pages.utils.job_utils import nodata_graph
import time
import cache_manager.cache_facade as cf
from components.visualization import VisualizationAIO

PAGE = "contributions"
VIZ_ID = "issue-staleness"


gc_issue_staleness = VisualizationAIO(
    PAGE,
    VIZ_ID,
    title="Issue Activity - Staleness",
    graph_info="""
    Visualizes growth of Issue backlog. Differentiates sub-populations\n
    of issues by their 'Staleness.'\n
    Please see the definition of 'Staleness' on the Info page.
    """,
    controls=[
        dbc.Row(
            [
                dbc.Label(
                    "Days Until Staling:",
                    html_for=f"staling-days-{PAGE}-{VIZ_ID}",
                    width={"size": "auto"},
                ),
                dbc.Col(
                    dbc.Input(
                        id=f"staling-days-{PAGE}-{VIZ_ID}",
                        type="number",
                        min=1,
                        max=120,
                        step=1,
                        value=7,
                        size="sm",
                        style={"width": "80px"},
                        className="dark-input",
                    ),
                    className="me-2",
                    width=2,
                ),
                dbc.Label(
                    "Days Until Stale:",
                    html_for=f"stale-days-{PAGE}-{VIZ_ID}",
                    width={"size": "auto"},
                ),
                dbc.Col(
                    dbc.Input(
                        id=f"stale-days-{PAGE}-{VIZ_ID}",
                        type="number",
                        min=1,
                        max=120,
                        step=1,
                        value=30,
                        size="sm",
                        style={"width": "80px"},
                        className="dark-input",
                    ),
                    className="me-2",
                    width=2,
                ),
                dbc.Alert(
                    children="Please ensure that 'Days Until Staling' is less than 'Days Until Stale'",
                    id=f"check-alert-{PAGE}-{VIZ_ID}",
                    dismissable=True,
                    fade=False,
                    is_open=False,
                    color="warning",
                ),
            ],
            align="center",
        ),
        dbc.Row(
            [
                dbc.Label(
                    "Date Interval:",
                    html_for=f"date-interval-{PAGE}-{VIZ_ID}",
                    width={"size": "auto"},
                ),
                dbc.Col(
                    [
                        dbc.RadioItems(
                            id=f"date-interval-{PAGE}-{VIZ_ID}",
                            options=[
                                {"label": "Trend", "value": "D"},
                                {"label": "Month", "value": "M"},
                                {"label": "Year", "value": "Y"},
                            ],
                            value="M",
                            inline=True,
                            className="custom-radio-buttons",
                        ),
                    ]
                ),
            ],
            align="center",
        ),
        dbc.Row(
            [
                dbc.Label(
                    "Issue Filter:",
                    html_for=f"bug-filter-{PAGE}-{VIZ_ID}",
                    width={"size": "auto"},
                ),
                dbc.Col(
                    dbc.RadioItems(
                        id=f"bug-filter-{PAGE}-{VIZ_ID}",
                        options=[
                            {"label": "All Issues", "value": "all"},
                            {"label": "Bugs Only", "value": "bug"},
                        ],
                        value="all",
                        inline=True,
                        className="custom-radio-buttons",
                    ),
                ),
            ],
            align="center",
        ),
    ],
    class_name="dark-card",
    id="issue-staleness",
)


@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    Output(f"check-alert-{PAGE}-{VIZ_ID}", "is_open"),
    [
        Input("repo-choices", "data"),
        Input(f"date-interval-{PAGE}-{VIZ_ID}", "value"),
        Input(f"staling-days-{PAGE}-{VIZ_ID}", "value"),
        Input(f"stale-days-{PAGE}-{VIZ_ID}", "value"),
        Input(f"bug-filter-{PAGE}-{VIZ_ID}", "value"),
    ],
    background=True,
)
def new_staling_issues_graph(repolist, interval, staling_interval, stale_interval, bug_filter):
    # conditional for the intervals to be valid options
    if staling_interval > stale_interval:
        return dash.no_update, True

    if staling_interval is None or stale_interval is None:
        return dash.no_update, dash.no_update

    # wait for data to asynchronously download and become available.

    while not_cached := cf.get_uncached(func_name=iq.__name__, repolist=repolist):
        logging.warning(f"ISSUES STALENESS - WAITING ON DATA TO BECOME AVAILABLE")
        time.sleep(0.5)

    # data ready.
    start = time.perf_counter()
    logging.warning("ISSUES STALENESS - START")

    # GET ALL DATA FROM POSTGRES CACHE
    df = cf.retrieve_from_cache(
        tablename=iq.__name__,
        repolist=repolist,
    )

    start = time.perf_counter()
    logging.warning("ISSUES STALENESS - START")

    # test if there is data
    if df.empty:
        logging.warning("ISSUE STALENESS - NO DATA AVAILABLE")
        return nodata_graph, False

    # function for all data pre processing
    df_status = process_data(df, interval, staling_interval, stale_interval, bug_filter)

    fig = create_figure(df_status, interval)

    logging.warning(f"ISSUE STALENESS - END - {time.perf_counter() - start}")
    return fig, False


def process_data(df: pd.DataFrame, interval, staling_interval, stale_interval, bug_filter):
    # convert to datetime objects rather than strings
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    df["closed_at"] = pd.to_datetime(df["closed_at"], utc=True)

    # filter to bug-tagged issues only if requested
    if bug_filter == "bug":
        if "labels" not in df.columns:
            logging.warning("ISSUE STALENESS - 'labels' column not found in cache, skipping bug filter")
        else:
            df = df[df["labels"].str.contains("bug", case=False, na=False)]

    # order values chronologically by creation date
    df = df.sort_values(by="created_at", axis=0, ascending=True)

    # first and last elements of the dataframe are the
    # earliest and latest events respectively
    earliest = df["created_at"].min()
    latest = max(df["created_at"].max(), df["closed_at"].max())

    # generating buckets beginning to the end of time by the specified interval
    dates = pd.date_range(start=earliest, end=latest, freq=interval, inclusive="both")

    # df for new, staling, and stale issues for time interval
    df_status = dates.to_frame(index=False, name="Date")

    # dynamically apply the function to all dates defined in the date_range to create df_status
    df_status["New"], df_status["Staling"], df_status["Stale"] = zip(
        *df_status.apply(
            lambda row: get_new_staling_stale_up_to(df, row.Date, staling_interval, stale_interval),
            axis=1,
        )
    )

    # formatting for graph generation
    if interval == "M":
        df_status["Date"] = df_status["Date"].dt.strftime("%Y-%m")
    elif interval == "Y":
        df_status["Date"] = df_status["Date"].dt.year

    return df_status


def create_figure(df_status: pd.DataFrame, interval):
    # time values for graph
    x_r, x_name, hover, period = get_graph_time_values(interval)

    # making a line graph if the bin-size is small enough.
    if interval == "D":
        fig = go.Figure(
            [
                go.Scatter(
                    name="New",
                    x=df_status["Date"],
                    y=df_status["New"],
                    mode="lines",
                    showlegend=True,
                    hovertemplate="Issues New: %{y}<br>%{x|%b %d, %Y} <extra></extra>",
                    marker=dict(color=baby_blue[0]),
                ),
                go.Scatter(
                    name="Staling",
                    x=df_status["Date"],
                    y=df_status["Staling"],
                    mode="lines",
                    showlegend=True,
                    hovertemplate="Issues Staling: %{y}<br>%{x|%b %d, %Y} <extra></extra>",
                    marker=dict(color=baby_blue[2]),
                ),
                go.Scatter(
                    name="Stale",
                    x=df_status["Date"],
                    y=df_status["Stale"],
                    mode="lines",
                    showlegend=True,
                    hovertemplate="Issues Stale: %{y}<br>%{x|%b %d, %Y} <extra></extra>",
                    marker=dict(color=baby_blue[6]),
                ),
            ]
        )
    else:
        fig = px.bar(
            df_status,
            x="Date",
            y=["New", "Staling", "Stale"],
            color_discrete_sequence=[baby_blue[0], baby_blue[2], baby_blue[6]],
        )

        # edit hover values
        fig.update_traces(hovertemplate=hover + "<br>Issues: %{y}<br>" + "<extra></extra>")

    fig.update_layout(
        xaxis_title="Time",
        yaxis_title="Issues",
        legend_title="Type",
        font=dict(size=14),
    )

    return fig


def get_new_staling_stale_up_to(df, date, staling_interval, stale_interval):
    # drop rows that are more recent than the date limit
    df_created = df[df["created_at"] <= date]

    # drop rows that have been closed before date
    df_in_range = df_created[df_created["closed_at"] > date]

    # include rows that have a null closed value
    df_in_range = pd.concat([df_in_range, df_created[df_created.closed_at.isnull()]])

    # time difference for the amount of days before the threshold date
    staling_days = date - relativedelta(days=+staling_interval)

    # time difference for the amount of days before the threshold date
    stale_days = date - relativedelta(days=+stale_interval)

    # issuess still open at the specified date
    numTotal = df_in_range.shape[0]

    # num of currently open issues that have been create in the last staling_value amount of days
    numNew = df_in_range[df_in_range["created_at"] >= staling_days].shape[0]

    staling = df_in_range[df_in_range["created_at"] > stale_days]
    numStaling = staling[staling["created_at"] < staling_days].shape[0]

    numStale = numTotal - (numNew + numStaling)

    return [numNew, numStaling, numStale]
