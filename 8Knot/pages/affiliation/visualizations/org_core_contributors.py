from dash import dcc, callback
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import pandas as pd
import logging
from dateutil.relativedelta import *  # type: ignore
import plotly.express as px
from pages.utils.graph_utils import baby_blue
from queries.affiliation_query import affiliation_query as aq
from pages.utils.job_utils import nodata_graph, POLL_INTERVAL_MS
import time
import datetime as dt
import app
import cache_manager.cache_facade as cf
from components.visualization import VisualizationAIO

PAGE = "affiliation"
VIZ_ID = "org-core-contributors"

gc_org_core_contributors = VisualizationAIO(
    PAGE,
    VIZ_ID,
    title="Organization Core Contributors",
    graph_info="""
    This graph counts the number of core contributions that COULD be linked to each organization.\n\
    The methodology behind this is to take each associated email to someones GitHub account\n\
    and link the contributions to each as it is unknown which initity the actvity was done for.\n\
    Then the graph groups contributions by contributors and filters by contributors that are core.\n\
    Contributions required is the amount of contributions necessary to be consider a core contributor\n\
    Core Contributors required is the amount of core contributors needed to have the domain listed.
    """,
    controls=[
        dbc.Row(
            [
                dbc.Label(
                    "Contributions Required:",
                    html_for=f"contributions-required-{PAGE}-{VIZ_ID}",
                    width={"size": "auto"},
                ),
                dbc.Col(
                    dbc.Input(
                        id=f"contributions-required-{PAGE}-{VIZ_ID}",
                        type="number",
                        min=1,
                        max=100,
                        step=1,
                        value=10,
                        size="sm",
                        className="dark-input",
                    ),
                    className="me-2",
                    width=2,
                ),
                dbc.Label(
                    "Core Contributors Required:",
                    html_for=f"contributors-required-{PAGE}-{VIZ_ID}",
                    width={"size": "auto"},
                ),
                dbc.Col(
                    dbc.Input(
                        id=f"contributors-required-{PAGE}-{VIZ_ID}",
                        type="number",
                        min=1,
                        max=50,
                        step=1,
                        value=3,
                        size="sm",
                        style={"width": "80px"},
                        className="dark-input",
                    ),
                    className="me-2",
                    width=2,
                ),
            ],
            align="center",
        ),
        dbc.Row(
            [
                dbc.Col(
                    dcc.DatePickerRange(
                        id=f"date-picker-range-{PAGE}-{VIZ_ID}",
                        min_date_allowed=dt.date(2005, 1, 1),
                        max_date_allowed=dt.date.today(),
                        initial_visible_month=dt.date(dt.date.today().year, 1, 1),
                        clearable=True,
                        className="dark-date-picker",
                    ),
                    # style={"marginTop": "1.7rem"},
                    width=7,
                ),
                dbc.Col(
                    dbc.Checklist(
                        id=f"email-filter-{PAGE}-{VIZ_ID}",
                        options=[
                            {
                                "label": "Exclude Gmail",
                                "value": "gmail",
                            },
                            {
                                "label": "Exclude GitHub",
                                "value": "github",
                            },
                        ],
                        value=[""],
                        inline=True,
                        switch=True,
                    ),
                    width=6,
                ),
            ],
            align="center",
            justify="between",
        ),
    ],
    class_name="dark-card",
    id="org-core-contributors",
)


# callback for Company Affiliation by Github Account Info graph
@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    [
        Input("repo-choices", "data"),
        Input(f"contributions-required-{PAGE}-{VIZ_ID}", "value"),
        Input(f"contributors-required-{PAGE}-{VIZ_ID}", "value"),
        Input(f"date-picker-range-{PAGE}-{VIZ_ID}", "start_date"),
        Input(f"date-picker-range-{PAGE}-{VIZ_ID}", "end_date"),
        Input(f"email-filter-{PAGE}-{VIZ_ID}", "value"),
        Input("bot-switch", "value"),
    ],
    background=True,
    interval=POLL_INTERVAL_MS,
)
def compay_associated_activity_graph(
    repolist,
    contributions,
    contributors,
    start_date,
    end_date,
    email_filter,
    bot_switch,
):
    # wait for data to asynchronously download and become available.
    while not_cached := cf.get_uncached(func_name=aq.__name__, repolist=repolist):
        logging.warning(f"{VIZ_ID}- WAITING ON DATA TO BECOME AVAILABLE")
        time.sleep(0.5)

    start = time.perf_counter()
    logging.warning(f"{VIZ_ID}- START")

    # GET ALL DATA FROM POSTGRES CACHE
    df = cf.retrieve_from_cache(
        tablename=aq.__name__,
        repolist=repolist,
    )

    # test if there is data
    if df.empty:
        logging.warning(f"{VIZ_ID} - NO DATA AVAILABLE")
        return nodata_graph

    # remove bot data
    if bot_switch:
        df = df[~df["cntrb_id"].isin(app.bots_list)]

    # function for all data pre processing, COULD HAVE ADDITIONAL INPUTS AND OUTPUTS
    df = process_data(df, contributions, contributors, start_date, end_date, email_filter)

    fig = create_figure(df)

    logging.warning(f"{VIZ_ID} - END - {time.perf_counter() - start}")
    return fig


def process_data(df: pd.DataFrame, contributions, contributors, start_date, end_date, email_filter):
    # convert to datetime objects rather than strings
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)

    # order values chronologically by COLUMN_TO_SORT_BY date
    df = df.sort_values(by="created_at", axis=0, ascending=True)

    # filter values based on date picker
    if start_date is not None:
        df = df[df.created_at >= start_date]
    if end_date is not None:
        df = df[df.created_at <= end_date]

    # groups contributions by countributor id and counts, created column now hold the number
    # of contributions for its respective contributor
    df = df.groupby(["cntrb_id", "email_list"], as_index=False)[["created_at"]].count()

    # filters out contributors that dont meet the core contribution threshhold
    df = df[df.created_at >= contributions]

    # creates list of unique emails and flattens list result
    emails = df.email_list.str.split(" , ").explode("email_list").tolist()

    # remove any entries not in email format and flattens list result
    emails = [x.lower() for x in emails if "@" in x]

    # creates list of email domains from the emails list
    email_domains = [x[x.rindex("@") + 1 :] for x in emails]

    # creates df of domains and counts
    df = pd.DataFrame(email_domains, columns=["domains"]).value_counts().to_frame().reset_index()

    df = df.rename(columns={"count": "contributors"})

    # changes the name of the org if under a certain threshold
    df.loc[df.contributors <= contributors, "domains"] = "Other"

    # groups others together for final counts
    df = (
        df.groupby(by="domains")["contributors"]
        .sum()
        .reset_index()
        .sort_values(by=["contributors"], ascending=False)
        .reset_index(drop=True)
    )

    # remove other from set
    df = df[df.domains != "Other"]

    # removes entries with gmail or other if checked
    if email_filter is not None:
        if "gmail" in email_filter:
            df = df[df.domains != "gmail.com"]
        if "github" in email_filter:
            df = df[df.domains != "users.noreply.github.com"]

    return df


def create_figure(df: pd.DataFrame):
    # graph generation
    fig = px.bar(df, x="domains", y="contributors", color_discrete_sequence=[baby_blue[8]])
    fig.update_xaxes(rangeslider_visible=True, range=[-0.5, 15])
    fig.update_layout(
        xaxis_title="Domains",
        yaxis_title="Core Contributors",
        bargroupgap=0.1,
        margin_b=40,
        font=dict(size=14),
    )
    fig.update_traces(
        hovertemplate="%{label} <br>Contributors: %{value}<br><extra></extra>",
    )

    return fig
