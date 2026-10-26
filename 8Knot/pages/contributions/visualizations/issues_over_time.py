from dash import dcc, callback
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import plotly.graph_objects as go
import pandas as pd
import logging
from pages.utils.graph_utils import get_graph_time_values, baby_blue
from pages.utils.job_utils import nodata_graph
from queries.issues_query import issues_query as iq
import time
import cache_manager.cache_facade as cf
import datetime as dt
from components.visualization import VisualizationAIO

PAGE = "contributions"
VIZ_ID = "issues-over-time"

gc_issues_over_time = VisualizationAIO(
    PAGE,
    VIZ_ID,
    title="Issues Over Time",
    graph_info="""
    Visualizes the activity of issues being Opened and Closed paritioned by time-window.\n
    Also shows the total volume of Open issues over time.
    """,
    controls=[
        dbc.Row(
            [
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
            align="center",
            justify="start",
        ),
        dbc.Row(
            dbc.Col(
                dcc.DatePickerRange(
                    id=f"date-picker-range-{PAGE}-{VIZ_ID}",
                    min_date_allowed=dt.date(2005, 1, 1),
                    max_date_allowed=dt.date.today(),
                    initial_visible_month=dt.date(dt.date.today().year, 1, 1),
                    clearable=True,
                    start_date=dt.date(
                        dt.date.today().year - 2,
                        dt.date.today().month,
                        dt.date.today().day,
                    ),
                    className="dark-date-picker",
                ),
                width=7,
            ),
        ),
        dbc.Row(
            [
                dbc.Label(
                    "Issue Filter:",
                    html_for=f"label-filter-{PAGE}-{VIZ_ID}",
                    width={"size": "auto"},
                ),
                dbc.Col(
                    dbc.RadioItems(
                        id=f"label-filter-{PAGE}-{VIZ_ID}",
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
    id="issues-over-time",
)


# callback for issues over time graph
@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    [
        Input("repo-choices", "data"),
        Input(f"date-interval-{PAGE}-{VIZ_ID}", "value"),
        Input(f"date-picker-range-{PAGE}-{VIZ_ID}", "start_date"),
        Input(f"date-picker-range-{PAGE}-{VIZ_ID}", "end_date"),
        Input(f"label-filter-{PAGE}-{VIZ_ID}", "value"),
    ],
    background=True,
)
def issues_over_time_graph(repolist, interval, start_date, end_date, label_filter):
    # wait for data to asynchronously download and become available.
    while not_cached := cf.get_uncached(func_name=iq.__name__, repolist=repolist):
        logging.warning(f"ISSUES OVER TIME - WAITING ON DATA TO BECOME AVAILABLE")
        time.sleep(0.5)

    # data ready.
    start = time.perf_counter()
    logging.warning("ISSUES OVER TIME - START")

    # GET ALL DATA FROM POSTGRES CACHE
    df = cf.retrieve_from_cache(
        tablename=iq.__name__,
        repolist=repolist,
    )

    # test if there is data
    if df.empty:
        logging.warning("ISSUES OVER TIME - NO DATA AVAILABLE")
        return nodata_graph

    # function for all data pre processing
    df_created, df_closed, df_open = process_data(df, interval, start_date, end_date, label_filter)

    fig = create_figure(df_created, df_closed, df_open, interval)

    logging.warning(f"ISSUES_OVER_TIME_VIZ - END - {time.perf_counter() - start}")

    return fig


def process_data(df: pd.DataFrame, interval, start_date, end_date, label_filter):
    # convert to datetime objects rather than strings
    df["created_at"] = pd.to_datetime(df["created_at"], utc=False)
    df["closed_at"] = pd.to_datetime(df["closed_at"], utc=False)

    # filter to bug-tagged issues only if requested
    if label_filter == "bug":
        if "labels" not in df.columns:
            logging.warning("ISSUES OVER TIME - 'labels' column not found in cache, skipping label filter")
        else:
            df = df[df["labels"].str.contains("bug", case=False, na=False)]

    # order values chronologically by creation date
    df = df.sort_values(by="created_at", axis=0, ascending=True)

    # variable to slice on to handle weekly period edge case
    period_slice = None
    if interval == "W":
        # this is to slice the extra period information that comes with the weekly case
        period_slice = 10

    # data frames for issues created or closed. Detailed description applies for all 3.

    # get the count of created issues in the desired interval in pandas period format, sort index to order entries
    created_range = pd.to_datetime(df["created_at"]).dt.to_period(interval).value_counts().sort_index()

    # converts to data frame object and creates date column from period values
    df_created = created_range.to_frame().reset_index().rename(columns={"created_at": "Date", "count": "created_at"})

    # converts date column to a datetime object, converts to string first to handle period information
    # the period slice is to handle weekly corner case
    df_created["Date"] = pd.to_datetime(df_created["Date"].astype(str).str[:period_slice])

    # df for closed issues in time interval
    closed_range = pd.to_datetime(df["closed_at"]).dt.to_period(interval).value_counts().sort_index()
    df_closed = closed_range.to_frame().reset_index().rename(columns={"closed_at": "Date", "count": "closed_at"})

    df_closed["Date"] = pd.to_datetime(df_closed["Date"].astype(str).str[:period_slice])

    # first and last elements of the dataframe are the
    # earliest and latest events respectively
    earliest = df["created_at"].min()
    latest = max(df["created_at"].max(), df["closed_at"].max())

    # filter values based on date picker, needs to be after open issue for correct counting
    if start_date is not None:
        df_created = df_created[df_created.Date >= start_date]
        df_closed = df_closed[df_closed.Date >= start_date]
        earliest = start_date
    if end_date is not None:
        df_created = df_created[df_created.Date <= end_date]
        df_closed = df_closed[df_closed.Date <= end_date]
        latest = end_date

    # beginning to the end of time by the specified interval
    dates = pd.date_range(start=earliest, end=latest, freq="D", inclusive="both")

    # df for open issues for time interval
    df_open = dates.to_frame(index=False, name="Date")

    # aplies function to get the amount of open issues for each day
    df_open["Open"] = df_open.apply(lambda row: get_open(df, row.Date), axis=1)

    # formatting for graph generation
    if interval == "M":
        df_created["Date"] = df_created["Date"].dt.strftime("%Y-%m-01")
        df_closed["Date"] = df_closed["Date"].dt.strftime("%Y-%m-01")
    elif interval == "Y":
        df_created["Date"] = df_created["Date"].dt.strftime("%Y-01-01")
        df_closed["Date"] = df_closed["Date"].dt.strftime("%Y-01-01")

    df_open["Date"] = df_open["Date"].dt.strftime("%Y-%m-%d")

    return df_created, df_closed, df_open


def create_figure(df_created: pd.DataFrame, df_closed: pd.DataFrame, df_open: pd.DataFrame, interval):
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
        name="Created",
    )
    fig.add_bar(
        x=df_closed["Date"],
        y=df_closed["closed_at"],
        opacity=0.9,
        hovertemplate=hover + "<br>Closed: %{y}<br>" + "<extra></extra>",
        offsetgroup=1,
        marker=dict(color=baby_blue[2]),
        name="Closed",
    )
    fig.update_layout(
        xaxis_title=x_name,
        yaxis_title="Number of Issues",
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
            hovertemplate="Issues Open: %{y}<br>%{x|%b %d, %Y} <extra></extra>",
        )
    )

    return fig


# for each day, this function calculates the amount of open issues
def get_open(df, date):
    # drop rows that are more recent than the date limit
    df_lim = df[df["created_at"] <= date]

    # drops rows that have been closed after date
    df_open = df_lim[df_lim["closed_at"] > date]

    # include issues that have not been close yet
    df_open = pd.concat([df_open, df_lim[df_lim.closed_at.isnull()]])

    # generates number of columns ie open issues
    num_open = df_open.shape[0]
    return num_open
