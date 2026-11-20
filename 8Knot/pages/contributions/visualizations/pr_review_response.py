from dash import callback
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import plotly.graph_objects as go
import pandas as pd
import logging
from dateutil.relativedelta import *  # type: ignore
from pages.utils.graph_utils import baby_blue
from queries.pr_response_query import pr_response_query as prr
from pages.utils.job_utils import nodata_graph, POLL_INTERVAL_MS
import time
import app
import cache_manager.cache_facade as cf
from components.visualization import VisualizationAIO

PAGE = "contributions"
VIZ_ID = "pr-review-response"

gc_pr_review_response = VisualizationAIO(
    PAGE,
    VIZ_ID,
    title="Pull Request Conversation Engagement",
    graph_info="""
    Tracks the number of PRs that are open on a given day vs. those that have
    received a comment or a review within a time interval, or that are waiting
    on a response from the opener.
    """,
    controls=[
        dbc.Label(
            "Response Days:",
            html_for=f"response-days-{PAGE}-{VIZ_ID}",
            width="auto",
        ),
        dbc.Col(
            dbc.Input(
                id=f"response-days-{PAGE}-{VIZ_ID}",
                type="number",
                min=1,
                max=120,
                step=1,
                value=2,
                size="sm",
                style={"width": "80px"},
                className="dark-input",
            ),
            className="me-2",
            width=2,
        ),
    ],
    class_name="dark-card",
    id="pr-review-response",
)


# callback for pr review response graph
@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    [
        Input("repo-choices", "data"),
        Input(f"response-days-{PAGE}-{VIZ_ID}", "value"),
        Input("bot-switch", "value"),
    ],
    background=True,
    interval=POLL_INTERVAL_MS,
)
def pr_review_response_graph(repolist, num_days, bot_switch):
    while not_cached := cf.get_uncached(func_name=prr.__name__, repolist=repolist):
        logging.warning(f"PR_FIRST_RESPONSE - WAITING ON DATA TO BECOME AVAILABLE")
        time.sleep(0.5)

    start = time.perf_counter()
    logging.warning(f"{VIZ_ID}- START")

    # GET ALL DATA FROM POSTGRES CACHE
    df = cf.retrieve_from_cache(
        tablename=prr.__name__,
        repolist=repolist,
    )

    # test if there is data
    if df.empty:
        logging.warning(f"{VIZ_ID} - NO DATA AVAILABLE")
        return nodata_graph

    # remove bot data
    if bot_switch:
        df = df[~df["cntrb_id"].isin(app.bots_list)]

    df = process_data(df, num_days)

    fig = create_figure(df, num_days)

    logging.warning(f"{VIZ_ID} - END - {time.perf_counter() - start}")
    return fig


def process_data(df: pd.DataFrame, num_days):
    # convert to datetime objects rather than strings
    df["msg_timestamp"] = pd.to_datetime(df["msg_timestamp"], utc=True)
    df["pr_created_at"] = pd.to_datetime(df["pr_created_at"], utc=True)
    df["pr_closed_at"] = pd.to_datetime(df["pr_closed_at"], utc=True)

    # sort in ascending earlier and only get ealiest value
    df = df.sort_values(by="msg_timestamp", axis=0, ascending=True)

    # 1 row per pr with either null msg date or most recent if one exists
    df = df.drop_duplicates(subset="pull_request_id", keep="last")

    # first and last elements of the dataframe are the
    # earliest and latest events respectively
    earliest = df["pr_created_at"].min()
    latest = max(df["pr_created_at"].max(), df["pr_closed_at"].max())

    # beginning to the end of time by the specified interval
    dates = pd.date_range(start=earliest, end=latest, freq="D", inclusive="both")

    # df for open prs and responded to prs in time interval
    df_pr_responses = dates.to_frame(index=False, name="Date")

    # every day, count the number of PRs that are open on that day and the number of
    # those that were responded to within num_days of their opening
    df_pr_responses["Open"], df_pr_responses["Response"] = zip(
        *df_pr_responses.apply(
            lambda row: get_open_response(df, row.Date, num_days),
            axis=1,
        )
    )

    df_pr_responses["Date"] = df_pr_responses["Date"].dt.strftime("%Y-%m-%d")

    return df_pr_responses


def create_figure(df: pd.DataFrame, num_days):
    fig = go.Figure(
        [
            go.Scatter(
                name="Prs Open",
                x=df["Date"],
                y=df["Open"],
                mode="lines",
                showlegend=True,
                hovertemplate="PR's Open: %{y}<br>%{x|%b %d, %Y} <extra></extra>",
                marker=dict(color=baby_blue[8]),
            ),
            go.Scatter(
                name="Response <" + str(num_days) + " days",
                x=df["Date"],
                y=df["Response"],
                mode="lines",
                showlegend=True,
                hovertemplate="PRs: %{y}<br>%{x|%b %d, %Y} <extra></extra>",
                marker=dict(color=baby_blue[2]),
            ),
        ]
    )
    fig.update_layout(
        xaxis_title="Time",
        yaxis_title="Number of PRs",
        font=dict(size=14),
    )

    return fig


def get_open_response(df, date, num_days):
    """
    This function takes a date and determines how many prs in that time interval are
    open and if they have a response within num_days or waiting on pr openers response.

    Args:
    -----
        df : Pandas Dataframe
            Dataframe with pr assignment actions of the assignees

        date : Datetime Timestamp
            Timestamp of the date

        num_days : int
            number of days that a response should be within

    Returns:
    --------
        int, int: number of open prs, and number of prs responded to within num_days or waiting on pr openers response
    """

    # drop rows with prs that have been created after the date
    df_created = df[df["pr_created_at"] <= date]

    # drops rows that have been closed before date
    df_open_at_date = df_created[df_created["pr_closed_at"] > date]

    # include prs that have not been close yet
    df_open_at_date = pd.concat([df_open_at_date, df_created[df_created.pr_closed_at.isnull()]])

    # number of columns in df ie number of open prs
    num_open = df_open_at_date.shape[0]

    # get all prs that have atleast one response
    df_response = df_open_at_date[df_open_at_date["msg_timestamp"].notnull()]

    # if no messages for any of the open prs, return num_open and 0
    if len(df_response.index) == 0:
        return num_open, 0

    # drop messages that happen after date considered
    df_messages_in_range = df_open_at_date[df_open_at_date["msg_timestamp"] < date]

    # order messages from earliest to latest by timestamp
    df_messages_in_range = df_messages_in_range.sort_values(by="msg_timestamp", axis=0, ascending=True)

    # threshold of when the last response would need to be by
    before_date_by_num_days = date - pd.DateOffset(days=num_days)

    # checks if the most recent message was within the date requirement or by someone other than
    # the pr creator
    df_responded_to_by_deadline = df_messages_in_range[
        (df_messages_in_range["msg_timestamp"] > before_date_by_num_days)
        | (df_messages_in_range["msg_cntrb_id"] != df_messages_in_range["cntrb_id"])
    ]

    # generates number of columns ie prs with a response within num_days or waiting on pr openers response
    n_met_response_criteria = df_responded_to_by_deadline.shape[0]

    return num_open, n_met_response_criteria
