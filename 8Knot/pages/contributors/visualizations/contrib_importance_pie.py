from dash import callback
import dash
from dash import dcc
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import pandas as pd
import logging
from dateutil.relativedelta import *  # type: ignore
import plotly.express as px
from pages.utils.graph_utils import baby_blue, contributor_label
from queries.contributors_query import contributors_query as ctq
from pages.utils.job_utils import nodata_graph
import time
import datetime as dt
import app
import pages.utils.preprocessing_utils as preproc_utils
import cache_manager.cache_facade as cf
from components.visualization import VisualizationAIO

PAGE = "contributors"
VIZ_ID = "contrib-importance-pie"

gc_contrib_importance_pie = VisualizationAIO(
    PAGE,
    VIZ_ID,
    graph_info="""
    AKA Bus factor. For a given action type, this visualizes the proportional share of the top k anonymous
    contributors, aggregating the remaining contributors as "Other". Suppose Contributor A
    opens the most PRs of all contributors, accounting for 1/5 of all PRs. If k = 1,
    then the chart will have one slice for Contributor A accounting for 1/5 of the area,
    with the remaining 4/5 representing all other contributors. Note: Some commits may have a
    Contributor ID of 'None' if there is no Github account is associated with the email that
    the contributor committed as.
    """,
    controls=[
        dbc.Row(
            [
                dbc.Label(
                    "Action Type:",
                    html_for=f"action-type-{PAGE}-{VIZ_ID}",
                    width={"size": "auto"},
                ),
                dbc.Col(
                    dcc.Dropdown(
                        id=f"action-type-{PAGE}-{VIZ_ID}",
                        options=[
                            {
                                "label": "Issue Opened",
                                "value": "Issue Opened",
                            },
                            {
                                "label": "Issue Comment",
                                "value": "Issue Comment",
                            },
                            {
                                "label": "Issue Closed",
                                "value": "Issue Closed",
                            },
                            {
                                "label": "PR Open",
                                "value": "PR Open",
                            },
                            {
                                "label": "PR Review",
                                "value": "PR Review",
                            },
                            {
                                "label": "PR Comment",
                                "value": "PR Comment",
                            },
                        ],
                        value="PR Review",
                        clearable=False,
                        className="dark-dropdown",
                    ),
                    className="me-2",
                    width=3,
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
                dbc.Label(
                    "Top K Contributors:",
                    html_for=f"top-k-contributors-{PAGE}-{VIZ_ID}",
                    width={"size": "auto"},
                ),
                dbc.Col(
                    dbc.Input(
                        id=f"top-k-contributors-{PAGE}-{VIZ_ID}",
                        type="number",
                        min=2,
                        max=100,
                        step=1,
                        value=10,
                        size="sm",
                        className="dark-input",
                    ),
                    className="me-2",
                    width=2,
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
            )
        ),
    ],
    class_name="dark-card",
    id="lottery-factor-snapshot",
)


# callback for dynamically changing the graph title
@callback(
    Output(f"graph-title-{PAGE}-{VIZ_ID}", "children"),
    Input(f"top-k-contributors-{PAGE}-{VIZ_ID}", "value"),
    Input(f"action-type-{PAGE}-{VIZ_ID}", "value"),
)
def graph_title(k, action_type):
    title = f"Lottery Factor: Top {k} Contributors by {action_type}"
    return title


# callback for contrib-importance graph
@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    Output(f"check-alert-{PAGE}-{VIZ_ID}", "is_open"),
    [
        Input("repo-choices", "data"),
        Input(f"action-type-{PAGE}-{VIZ_ID}", "value"),
        Input(f"top-k-contributors-{PAGE}-{VIZ_ID}", "value"),
        Input(f"date-picker-range-{PAGE}-{VIZ_ID}", "start_date"),
        Input(f"date-picker-range-{PAGE}-{VIZ_ID}", "end_date"),
        Input("bot-switch", "value"),
    ],
    background=True,
)
def create_top_k_cntrbs_graph(repolist, action_type, top_k, start_date, end_date, bot_switch):
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
        bots_list = app.bots_list
        df = df[~df["cntrb_id"].isin(bots_list)]

    # checks if there is a contribution of a specfic action type in repo set
    if not df["Action"].str.contains(action_type).any():
        return dash.no_update, True

    # function for all data pre processing
    df = process_data(df, action_type, top_k, start_date, end_date)

    fig = create_figure(df, action_type)

    logging.warning(f"{VIZ_ID} - END - {time.perf_counter() - start}")
    return fig, False


def process_data(df: pd.DataFrame, action_type, top_k, start_date, end_date):
    # convert to datetime objects rather than strings
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)

    # order values chronologically by created_at date
    df = df.sort_values(by="created_at", ascending=True)

    # filter values based on date picker
    if start_date is not None:
        df = df[df.created_at >= start_date]
    if end_date is not None:
        df = df[df.created_at <= end_date]

    # subset the df such that it only contains rows where the Action column value is the action type
    df = df[df["Action"].str.contains(action_type)]

    # get the number of total contributions of the specific action type
    t_sum = df.shape[0]

    # count the number of contributions for each contributor
    label_col, _ = contributor_label()

    # not every contributor has a GitHub account, so keep the id where login is null
    if label_col != "cntrb_id":
        df[label_col] = df[label_col].fillna(df["cntrb_id"])

    df = (df.groupby(label_col)["Action"].count()).to_frame()

    # sort rows according to amount of contributions from greatest to least
    df.sort_values(by="Action", ascending=False, inplace=True)

    df = df.reset_index()

    # rename Action column to action_type
    df = df.rename(columns={"Action": action_type})

    # get the number of total contributions
    t_sum = df[action_type].sum()

    # index df to get first k rows
    df = df.head(top_k)

    # get the number of total top k contributions
    df_sum = df[action_type].sum()

    # calculate the remaining contributions by taking the the difference of t_sum and df_sum
    # dataframes no longer implement above 'append' interface as of Pandas 1.4.4
    # create a single-entry dataframe that we can concatenate onto existing df
    df_concat = pd.DataFrame(data={label_col: ["Other"], action_type: [t_sum - df_sum]})
    df = pd.concat([df, df_concat], ignore_index=True)

    return df


def create_figure(df: pd.DataFrame, action_type):
    label_col, label_name = contributor_label()

    # create plotly express pie chart
    fig = px.pie(
        df,
        names=label_col,
        values=action_type,
        color_discrete_sequence=baby_blue,
    )

    # display percent contributions and the contributor label in each wedge
    # format hover template to display the contributor label and their contribution count for the action_type
    fig.update_traces(
        textinfo="percent+label",
        textposition="inside",
        hovertemplate=f"{label_name}: %{{label}} <br>Contributions: %{{value}}<br><extra></extra>",
    )

    return fig
