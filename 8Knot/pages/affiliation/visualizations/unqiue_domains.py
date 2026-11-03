from dash import dcc, callback
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import pandas as pd
import logging
from dateutil.relativedelta import *  # type: ignore
import plotly.express as px
from pages.utils.graph_utils import baby_blue
from queries.commits_query import commits_query as cmq
from pages.utils.job_utils import nodata_graph
import time
import datetime as dt
import app
import cache_manager.cache_facade as cf
from components.visualization import VisualizationAIO

PAGE = "affiliation"
VIZ_ID = "unique-domains"

gc_unique_domains = VisualizationAIO(
    PAGE,
    VIZ_ID,
    title="Unique Commit Email Domains",
    graph_info="""
    Visualizes the proportion of commit activity associated with specific author email domains.\n
    e.g. if there are 100 commits and 50 were authored with an '@gmail.com' address and 50 with\n
    '@redhat.com', each domain will represent half of the chart. This uses the same commit data\n
    as Commit Activity by Domain.
    """,
    controls=[
        dbc.Label(
            "Contributors Required:",
            html_for=f"contributions-required-{PAGE}-{VIZ_ID}",
            width={"size": "auto"},
        ),
        dbc.Col(
            dbc.Input(
                id=f"contributions-required-{PAGE}-{VIZ_ID}",
                type="number",
                min=1,
                max=50,
                step=1,
                value=3,
                size="sm",
                className="dark-input",
            ),
            width=2,
        ),
        dbc.Col(
            dcc.DatePickerRange(
                id=f"date-picker-range-{PAGE}-{VIZ_ID}",
                min_date_allowed=dt.date(2005, 1, 1),
                max_date_allowed=dt.date.today(),
                initial_visible_month=dt.date(dt.date.today().year, 1, 1),
                clearable=True,
                className="dark-date-picker",
            ),
            width=7,
        ),
    ],
    class_name="dark-card",
    id="unique-domains",
)


@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    [
        Input("repo-choices", "data"),
        Input(f"contributions-required-{PAGE}-{VIZ_ID}", "value"),
        Input(f"date-picker-range-{PAGE}-{VIZ_ID}", "start_date"),
        Input(f"date-picker-range-{PAGE}-{VIZ_ID}", "end_date"),
        Input("bot-switch", "value"),
    ],
    background=True,
)
def unique_domains_graph(repolist, num, start_date, end_date, bot_switch):
    # wait for data to asynchronously download and become available.
    cf.wait_for_cache(func_name=cmq.__name__, repolist=repolist)

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
    df = process_data(df, num, start_date, end_date)

    fig = create_figure(df)

    logging.warning(f"{VIZ_ID} - END - {time.perf_counter() - start}")
    return fig


def process_data(df: pd.DataFrame, num, start_date, end_date):
    # convert to datetime objects rather than strings
    df["author_timestamp"] = pd.to_datetime(df["author_timestamp"], utc=True)

    # order values chronologically by author_timestamp date earliest to latest
    df = df.sort_values(by="author_timestamp", axis=0, ascending=True)

    # filter values based on date picker
    if start_date is not None:
        df = df[df.author_timestamp >= start_date]
    if end_date is not None:
        df = df[df.author_timestamp <= end_date]

    # one author email per commit
    emails = df.author_email.tolist()

    # remove any entries not in email format and put all emails in lowercase
    emails = [x.lower() for x in emails if isinstance(x, str) and "@" in x]

    # creates list of email domains from the emails list
    email_domains = [x[x.rindex("@") + 1 :] for x in emails]

    # creates df of domains and counts
    df = pd.DataFrame(email_domains, columns=["domains"]).value_counts().to_frame().reset_index()

    df = df.rename(columns={"count": "occurrences"})

    # changes the name of the company if under a certain threshold
    df.loc[df["occurrences"] <= num, "domains"] = "Other"

    # groups others together for final counts
    df = (
        df.groupby(by="domains")["occurrences"]
        .sum()
        .reset_index()
        .sort_values(by=["occurrences"], ascending=False)
        .reset_index(drop=True)
    )

    return df


def create_figure(df: pd.DataFrame):
    # graph generation
    fig = px.pie(df, names="domains", values="occurrences", color_discrete_sequence=baby_blue)
    fig.update_traces(
        textposition="inside",
        textinfo="percent+label",
        hovertemplate="%{label} <br>Contributors: %{value}<br><extra></extra>",
    )

    return fig
