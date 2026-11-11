from dash import callback
import dash
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import logging
from dateutil.relativedelta import *  # type: ignore
import plotly.express as px
from pages.utils.graph_utils import get_graph_time_values, baby_blue
from pages.utils.job_utils import nodata_graph
import time
import app
from queries.contributors_query import contributors_query as ctq
import pages.utils.preprocessing_utils as preproc_utils
import cache_manager.cache_facade as cf
from components.visualization import VisualizationAIO

PAGE = "contributors"
VIZ_ID = "active-drifting-contributors"

gc_active_drifting_contributors = VisualizationAIO(
    PAGE,
    VIZ_ID,
    title="Contributor Growth by Engagement",
    graph_info="""
    Visualizes growth of contributor population, including sub-populations\n
    in consideration of how recently a contributor has contributed.\n
    Please see definitions of 'Contributor Recency' on Info page.
    """,
    controls=[
        dbc.Row(
            [
                dbc.Label(
                    "Months Until Drifting:",
                    html_for=f"drifting-months-{PAGE}-{VIZ_ID}",
                    width={"size": "auto"},
                ),
                dbc.Col(
                    dbc.Input(
                        id=f"drifting-months-{PAGE}-{VIZ_ID}",
                        type="number",
                        min=1,
                        max=120,
                        step=1,
                        value=6,
                        size="sm",
                        style={"width": "80px"},
                        className="dark-input",
                    ),
                    className="me-2",
                    width=2,
                ),
                dbc.Label(
                    "Months Until Away:",
                    html_for=f"away-months-{PAGE}-{VIZ_ID}",
                    width={"size": "auto"},
                ),
                dbc.Col(
                    dbc.Input(
                        id=f"away-months-{PAGE}-{VIZ_ID}",
                        type="number",
                        min=1,
                        max=120,
                        step=1,
                        value=12,
                        size="sm",
                        style={"width": "80px"},
                        className="dark-input",
                    ),
                    className="me-2",
                    width=2,
                ),
                dbc.Alert(
                    children="Please ensure that 'Months Until Drifting' is less than 'Months Until Away'",
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
    ],
    class_name="dark-card",
    id="engagement-growth",
)


@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    Output(f"check-alert-{PAGE}-{VIZ_ID}", "is_open"),
    [
        Input("repo-choices", "data"),
        Input(f"date-interval-{PAGE}-{VIZ_ID}", "value"),
        Input(f"drifting-months-{PAGE}-{VIZ_ID}", "value"),
        Input(f"away-months-{PAGE}-{VIZ_ID}", "value"),
        Input("bot-switch", "value"),
    ],
    background=True,
)
def active_drifting_contributors_graph(repolist, interval, drift_interval, away_interval, bot_switch):
    # conditional for the intervals to be valid options
    if drift_interval is None or away_interval is None:
        return dash.no_update, dash.no_update

    if drift_interval > away_interval:
        return dash.no_update, True

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
        logging.warning("ACTIVE_DRIFTING_CONTRIBUTOR_GROWTH - NO DATA AVAILABLE")
        return nodata_graph, False

    # remove bot data
    if bot_switch:
        df = df[~df["cntrb_id"].isin(app.bots_list)]

    # function for all data pre processing
    df_status = process_data(df, interval, drift_interval, away_interval)

    fig = create_figure(df_status, interval)

    logging.warning(f"ACTIVE_DRIFTING_CONTRIBUTOR_GROWTH_VIZ - END - {time.perf_counter() - start}")
    return fig, False


def process_data(df: pd.DataFrame, interval, drift_interval, away_interval):
    # convert to datetime objects with consistent column name
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    # df.rename(columns={"created_at": "created"}, inplace=True)

    # order from beginning of time to most recent
    df = df.sort_values("created_at", axis=0, ascending=True)

    # first and last elements of the dataframe are the
    # earliest and latest events respectively
    earliest, latest = df["created_at"].min(), df["created_at"].max()

    # beginning to the end of time by the specified interval
    dates = pd.date_range(start=earliest, end=latest, freq=interval, inclusive="both")

    # df for active, driving, and away contributors for time interval
    df_status = dates.to_frame(index=False, name="Date")

    # active, drifting, and away contributor counts for every date in the date_range
    df_status["Active"], df_status["Drifting"], df_status["Away"] = zip(
        *get_active_drifting_away_counts(df, dates, drift_interval, away_interval)
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
                    name="Active",
                    x=df_status["Date"],
                    y=df_status["Active"],
                    mode="lines",
                    showlegend=True,
                    hovertemplate="Contributors Active: %{y}<br>%{x|%b %d, %Y} <extra></extra>",
                    marker=dict(color=baby_blue[6]),
                ),
                go.Scatter(
                    name="Drifting",
                    x=df_status["Date"],
                    y=df_status["Drifting"],
                    mode="lines",
                    showlegend=True,
                    hovertemplate="Contributors Drifting: %{y}<br>%{x|%b %d, %Y} <extra></extra>",
                    marker=dict(color=baby_blue[2]),
                ),
                go.Scatter(
                    name="Away",
                    x=df_status["Date"],
                    y=df_status["Away"],
                    mode="lines",
                    showlegend=True,
                    hovertemplate="Contributors Away: %{y}<br>%{x|%b %d, %Y} <extra></extra>",
                    marker=dict(color=baby_blue[0]),
                ),
            ]
        )
    else:
        fig = px.bar(
            df_status,
            x="Date",
            y=["Active", "Drifting", "Away"],
            color_discrete_sequence=[baby_blue[6], baby_blue[2], baby_blue[0]],
        )

        # edit hover values
        fig.update_traces(hovertemplate=hover + "<br>Contributors: %{y}<br>" + "<extra></extra>")

    fig.update_layout(
        xaxis_title="Time",
        yaxis_title="Number of Contributors",
        legend_title="Type",
        font=dict(size=14),
    )

    return fig


def get_active_drifting_away_counts(df, dates, drift_interval, away_interval):
    """[active, drifting, away] contributor counts at each date, judged by each contributor's latest activity up to it.

    df must be sorted by created_at. An activity is its contributor's latest from its own time until their next one,
    so each date only checks the activities inside its drift/away window instead of filtering every row.
    """
    # one row per contributor per timestamp, so a contributor's next activity is strictly later
    events = df.drop_duplicates(subset=["cntrb_id", "created_at"])
    created = events["created_at"].dt.as_unit("ns").astype("int64").to_numpy()
    next_activity = events.groupby("cntrb_id")["created_at"].shift(-1).dt.as_unit("ns")
    next_activity = next_activity.fillna(pd.Timestamp.max.tz_localize("UTC")).astype("int64").to_numpy()
    first_activity = created[~events["cntrb_id"].duplicated().to_numpy()]

    counts = []
    for date in dates:
        drift_mos = (date - relativedelta(months=+drift_interval)).value
        away_mos = (date - relativedelta(months=+away_interval)).value
        # activities in (away_mos, drift_mos) and [drift_mos, date]
        after_away = np.searchsorted(created, away_mos, side="right")
        from_drift = np.searchsorted(created, drift_mos, side="left")
        up_to_date = np.searchsorted(created, date.value, side="right")
        # an activity is its contributor's latest at date if they don't act again by then
        num_active = np.count_nonzero(next_activity[from_drift:up_to_date] > date.value)
        num_drifting = np.count_nonzero(next_activity[after_away:from_drift] > date.value)
        num_total = np.searchsorted(first_activity, date.value, side="right")
        counts.append([num_active, num_drifting, num_total - (num_active + num_drifting)])
    return counts
