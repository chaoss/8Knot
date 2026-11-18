from dash import callback
import dash
from dash import dcc
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import logging
from dateutil.relativedelta import *  # type: ignore
from pages.utils.graph_utils import baby_blue
from queries.contributors_query import contributors_query as ctq
from pages.utils.job_utils import nodata_graph, POLL_INTERVAL_MS
import time
import app
import pages.utils.preprocessing_utils as preproc_utils
import cache_manager.cache_facade as cf
from components.visualization import VisualizationAIO

PAGE = "contributors"
VIZ_ID = "lottery-factor-over-time"

gc_lottery_factor_over_time = VisualizationAIO(
    PAGE,
    VIZ_ID,
    title="Lottery Factor: 6 Month Windows",
    graph_info="""
    This analysis is also referred to as "Bus Factor". For each action type, visualizes
    the smallest group of contributors who account for a user-inputted percentage
    of the total number of contributions. By default, the threshold is set to 50%.
    Thus, the visualization will show the number of contributors who account for
    50% of all contributions made, per action type. Suppose two individuals authored
    50% of the commits, then the contributor prolificacy is 2. Analysis is done over
    a time range, and snapshots of the time range are set according to window width
    and step size. By default, window width and step size are set to 6 months.
    Thus, contributor prolificacy is calculated for each non-overlapping 6-month
    snapshot of the time range provided. Optionally, contributors who have 'bot' or
    any custom keyword(s) in their logins can be filtered out. Please note that gaps
    in the graph indicate that no contributions of a specific action type(s) were made
    during that time period.
    """,
    controls=[
        dbc.Row(
            [
                dbc.Label(
                    "Window Width (Months):",
                    html_for=f"window-width-{PAGE}-{VIZ_ID}",
                    width={"size": "auto"},
                ),
                dbc.Col(
                    dbc.Input(
                        id=f"window-width-{PAGE}-{VIZ_ID}",
                        type="number",
                        min=1,
                        max=12,
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
                    "Step Size (Months):",
                    html_for=f"step-size-{PAGE}-{VIZ_ID}",
                    width="auto",
                ),
                dbc.Col(
                    dbc.Input(
                        id=f"step-size-{PAGE}-{VIZ_ID}",
                        type="number",
                        min=1,
                        max=12,
                        step=1,
                        value=6,
                        size="sm",
                        style={"width": "80px"},
                        className="dark-input",
                    ),
                    className="me-2",
                    width=2,
                ),
                dbc.Alert(
                    children="Please ensure that 'Step Size' is less than or equal to 'Window Size'",
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
                    "Threshold:",
                    html_for=f"threshold-{PAGE}-{VIZ_ID}",
                    width={"size": "auto"},
                ),
                dbc.Col(
                    [
                        dcc.Slider(
                            id=f"threshold-{PAGE}-{VIZ_ID}",
                            min=10,
                            max=95,
                            value=50,
                            marks={i: f"{i}%" for i in range(10, 100, 5)},
                            className="dark-slider",
                        ),
                    ],
                    className="me-2",
                    width=9,
                ),
            ],
            align="center",
        ),
    ],
    class_name="dark-card",
    id="lottery-factor-time",
)


# callback for dynamically changing the graph title
@callback(
    Output(f"graph-title-{PAGE}-{VIZ_ID}", "children"),
    Input(f"window-width-{PAGE}-{VIZ_ID}", "value"),
)
def graph_title(window_width):
    title = f"Lottery Factor: {window_width} Month Windows"
    return title


# callback for lottery-factor-over-time graph
@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    Output(f"check-alert-{PAGE}-{VIZ_ID}", "is_open"),
    [
        Input("repo-choices", "data"),
        Input(f"threshold-{PAGE}-{VIZ_ID}", "value"),
        Input(f"window-width-{PAGE}-{VIZ_ID}", "value"),
        Input(f"step-size-{PAGE}-{VIZ_ID}", "value"),
        Input("bot-switch", "value"),
    ],
    background=True,
    interval=POLL_INTERVAL_MS,
)
def create_contrib_prolificacy_over_time_graph(repolist, threshold, window_width, step_size, bot_switch):
    # wait for data to asynchronously download and become available.
    while not_cached := cf.get_uncached(func_name=ctq.__name__, repolist=repolist):
        logging.warning(f"{VIZ_ID}- WAITING ON DATA TO BECOME AVAILABLE")
        time.sleep(0.5)

    start = time.perf_counter()
    logging.warning(f"{VIZ_ID} - START")

    # GET ALL DATA FROM POSTGRES CACHE
    df = cf.retrieve_from_cache(
        tablename=ctq.__name__,
        repolist=repolist,
    )

    df = preproc_utils.contributors_df_action_naming(df)

    # remove bot data
    if bot_switch:
        df = df[~df["cntrb_id"].isin(app.bots_list)]

    # test if there is data
    if df.empty:
        logging.warning(f"{VIZ_ID} - NO DATA AVAILABLE")
        return nodata_graph, False

    # if the step size is greater than window width raise Alert
    if step_size > window_width:
        return dash.no_update, True

    df = process_data(df, threshold, window_width, step_size)

    fig = create_figure(df, threshold, step_size)

    logging.warning(f"{VIZ_ID} - END - {time.perf_counter() - start}")
    return fig, False


def process_data(df, threshold, window_width, step_size):
    # convert to datetime objects rather than strings
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)

    # order values chronologically by created_at date
    df = df.sort_values(by="created_at", ascending=True)

    # get start and end date from created column
    start_date = df["created_at"].min()
    end_date = df["created_at"].max()

    # convert percent to its decimal representation
    threshold = threshold / 100

    # create bins with a size equivalent to the the step size starting from the start date up to the end date
    period_from = pd.date_range(start=start_date, end=end_date, freq=f"{step_size}m", inclusive="both")
    # store the period_from dates in a df
    df_final = period_from.to_frame(index=False, name="period_from")
    # calculate the end of each interval and store the values in a column named period_from
    df_final["period_to"] = df_final["period_from"] + pd.DateOffset(months=window_width)

    # dynamically calculate the contributor prolificacy over time for each of the action times and store results in df_final
    (
        df_final["Issue Opened"],
        df_final["Issue Comment"],
        df_final["Issue Closed"],
        df_final["PR Opened"],
        df_final["PR Comment"],
        df_final["PR Review"],
    ) = zip(
        *df_final.apply(
            lambda row: cntrb_prolificacy_over_time(df, row.period_from, row.period_to, window_width, threshold),
            axis=1,
        )
    )

    return df_final


def create_figure(df_final, threshold, step_size):
    # create custom data to update the hovertemplate with the action type and start and end dates of a given time window in addition to the lottery factor
    # make a nested list of plural action types so that it is gramatically correct in the updated hover info eg. Commit -> Commits and PR Opened -> PRs Opened
    action_types = [
        (
            [action_type[:2] + "s" + action_type[2:]] * len(df_final)
            if action_type == "PR Opened"
            else (
                [action_type[:5] + "s" + action_type[5:]] * len(df_final)
                if action_type == "Issue Opened" or action_type == "Issue Closed"
                else [action_type + "s"] * len(df_final)
            )
        )
        for action_type in df_final.columns[2:]
    ]
    time_window = list(
        df_final["period_from"].dt.strftime("%b %d, %Y") + " - " + df_final["period_to"].dt.strftime("%b %d, %Y")
    )
    customdata = np.stack(([threshold] * len(df_final), time_window), axis=-1)

    # create plotly express line graph
    fig = go.Figure(
        [
            go.Scatter(
                name="Issue Opened",
                x=df_final["period_from"],
                y=df_final["Issue Opened"],
                text=action_types[0],
                customdata=customdata,
                mode="lines",
                showlegend=True,
                marker=dict(color=baby_blue[2]),
            ),
            go.Scatter(
                name="Issue Comment",
                x=df_final["period_from"],
                y=df_final["Issue Comment"],
                text=action_types[1],
                customdata=customdata,
                mode="lines",
                showlegend=True,
                marker=dict(color=baby_blue[4]),
            ),
            go.Scatter(
                name="Issue Closed",
                x=df_final["period_from"],
                y=df_final["Issue Closed"],
                text=action_types[2],
                customdata=customdata,
                mode="lines",
                showlegend=True,
                marker=dict(color=baby_blue[6]),
            ),
            go.Scatter(
                name="PR Opened",
                x=df_final["period_from"],
                y=df_final["PR Opened"],
                text=action_types[3],
                customdata=customdata,
                mode="lines",
                showlegend=True,
                marker=dict(color=baby_blue[9]),
            ),
            go.Scatter(
                name="PR Comment",
                x=df_final["period_from"],
                y=df_final["PR Comment"],
                text=action_types[4],
                customdata=customdata,
                mode="lines",
                showlegend=True,
                marker=dict(color=baby_blue[8]),
            ),
            go.Scatter(
                name="PR Review",
                x=df_final["period_from"],
                y=df_final["PR Review"],
                text=action_types[5],
                customdata=customdata,
                mode="lines",
                showlegend=True,
                marker=dict(color=baby_blue[10]),
            ),
        ],
    )

    # define x-axis and y-axis titles and intialize first x-axis tick to start at the user-inputted start_date
    start_date = min(df_final["period_from"])

    # update xaxes to display ticks, only show ticks every other year
    fig.update_xaxes(
        showgrid=True,
        ticklabelmode="period",
        tickangle=0,
        dtick=f"M24",
        tickformat="%b %Y",
    )

    # hover template styling
    fig.update_traces(
        textposition="top right",
        hovertemplate="%{y} people contributing to<br>%{customdata[0]}% of %{text} from<br>%{customdata[1]}<br><extra></extra>",
    )

    # update xaxes to show only the year
    fig.update_xaxes(showgrid=True, ticklabelmode="period", dtick="M12", tickformat="%Y")

    # layout styling
    fig.update_layout(
        xaxis_title=f"Timeline (stepsize = {step_size} months)",
        yaxis_title="Lottery Factor",
        font=dict(size=14),
        margin_b=40,
        legend_title="Action Type",
    )

    return fig


def cntrb_prolificacy_over_time(df, period_from, period_to, window_width, threshold):
    # subset df such that the rows correspond to the window of time defined by period from and period to
    time_mask = (df["created_at"] >= period_from) & (df["created_at"] <= period_to)
    df_in_range = df.loc[time_mask]

    # initialize varibles to store contributor prolificacy accoding to action type
    issueOpened, issueComment, issueClosed, prOpened, prReview, prComment = (
        None,
        None,
        None,
        None,
        None,
        None,
    )

    # count the number of contributions each contributor has made according each action type
    df_count_cntrbs = df_in_range.groupby(["Action", "cntrb_id"])["cntrb_id"].count().to_frame()
    df_count_cntrbs = df_count_cntrbs.rename(columns={"cntrb_id": "count"}).reset_index()

    # pivot df such that the column names correspond to the different action types, index is the cntrb_ids, and the values are the number of contributions of each contributor
    df_count_cntrbs = df_count_cntrbs.pivot(index="cntrb_id", columns="Action", values="count")

    issueOpened = calc_lottery_factor(df_count_cntrbs, "Issue Opened", threshold)
    issueComment = calc_lottery_factor(df_count_cntrbs, "Issue Comment", threshold)
    issueClosed = calc_lottery_factor(df_count_cntrbs, "Issue Closed", threshold)
    prOpened = calc_lottery_factor(df_count_cntrbs, "PR Opened", threshold)
    prReview = calc_lottery_factor(df_count_cntrbs, "PR Review", threshold)
    prComment = calc_lottery_factor(df_count_cntrbs, "PR Comment", threshold)

    return issueOpened, issueComment, issueClosed, prOpened, prReview, prComment


def calc_lottery_factor(df, action_type, threshold):
    # if the df is empty return None
    if df.empty:
        return None

    # if the specified action type is not in the dfs' cols return None
    if action_type not in df.columns:
        return None

    # sort rows in df based on number of contributions from greatest to least
    df = df.sort_values(by=action_type, ascending=False)

    # calculate the threshold amount of contributions
    thresh_cntrbs = df[action_type].sum() * threshold

    # drop rows where the cntrb_id is None
    mask = df.index.get_level_values("cntrb_id") == None
    df = df[~mask]

    # initilize running sum of contributors who make up contributor prolificacy
    lottery_factor = 0

    # initialize running sum of contributions
    running_sum = 0

    for _, row in df.iterrows():
        running_sum += row[action_type]  # update the running sum by the number of contributions a contributor has made
        lottery_factor += 1  # update contributor prolificacy
        # if the running sum of contributions is greater than or equal to the threshold amount, break
        if running_sum >= thresh_cntrbs:
            break

    return lottery_factor
