from dash import dcc, callback
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import pandas as pd
import logging
from dateutil.relativedelta import *  # type: ignore
import plotly.express as px
from pages.utils.graph_utils import baby_blue
from queries.affiliation_query import affiliation_query as aq
from pages.utils.job_utils import nodata_graph
import time
import datetime as dt
import app
import cache_manager.cache_facade as cf
from components.visualization import VisualizationAIO

PAGE = "affiliation"
VIZ_ID = "organization-associated-activity"

gc_org_associated_activity = VisualizationAIO(
    PAGE,
    VIZ_ID,
    title="Organization Associated Activity",
    graph_info="""
    For non-commit contributions (see definition of Contribution on Info page)\n
    we only know which contributor account contributed. We don't know which email,\n
    and therefore which possible institution the contribution represented.\n
    e.g. if we know that a PR comment was made by JaneDoe, and they have a '@redhat.com' and\n
    an '@gmail.com' email, we don't know whether they contributed individually\n
    or as a representative of an instituion. Therefore, we lower-bound the contribution\n
    of representation by counting each contribution as being made by ALL of the contributors\n
    linked email domains.\n
    This graph can therefore be interpreted as 'The minimum number of individuals who have\n
    been associated with each domain.'\n
    e.g. If there are 100 contributions and 20 contributors, and each contributor has an '@redhat.com'\n
    email associated with their account and one other random email, '@redhat.com' will be counted 100 times\n
    and the other contributor emails will also total a count of 100.\n
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
            justify="start",
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
                    width=7,
                ),
            ],
            justify="start",
        ),
    ],
    class_name="dark-card",
    id="org-activity",
)


# callback for Organization Affiliation by Github Account Info graph
@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    [
        Input("repo-choices", "data"),
        Input(f"contributions-required-{PAGE}-{VIZ_ID}", "value"),
        Input(f"date-picker-range-{PAGE}-{VIZ_ID}", "start_date"),
        Input(f"date-picker-range-{PAGE}-{VIZ_ID}", "end_date"),
        Input(f"email-filter-{PAGE}-{VIZ_ID}", "value"),
        Input("bot-switch", "value"),
    ],
    background=True,
)
def org_associated_activity_graph(repolist, num, start_date, end_date, email_filter, bot_switch):
    """Each contribution is associated with a contributor. That contributor can be associated with

    more than one different email. Hence each contribution is associated with all of the emails that a contributor has historically used.

    We don't always know which email (and therefore which organization) a contributor is affiliated with at contribution

    time, so we choose to count all of their possible affiliations via their email list. e.g. if "Jane Doe" is associated with "gmail.com"

    and "yahoo.com" and they have 5 contributions, "gmail.com" and "yahoo.com" would be counted 5 times each. We assume that relatively few people

    will have many emails. We acknowledge that this will almost always contribute to an overcount but will never undercount."
    """

    # wait for data to asynchronously download and become available.
    cf.wait_for_cache(func_name=aq.__name__, repolist=repolist)

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
    df = process_data(df, num, start_date, end_date, email_filter)

    fig = create_figure(df)

    logging.warning(f"{VIZ_ID} - END - {time.perf_counter() - start}")
    return fig


def process_data(df: pd.DataFrame, num, start_date, end_date, email_filter):
    # convert to datetime objects rather than strings
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)

    # order values chronologically by COLUMN_TO_SORT_BY date
    df = df.sort_values(by="created_at", axis=0, ascending=True)

    # filter values based on date picker
    if start_date is not None:
        df = df[df.created_at >= start_date]
    if end_date is not None:
        df = df[df.created_at <= end_date]

    # creates list of emails for each contribution and flattens list result
    emails = df.email_list.str.split(" , ").explode("email_list").tolist()

    # remove any entries not in email format and flattens list result
    emails = [x.lower() for x in emails if "@" in x]

    # creates list of email domains from the emails list
    email_domains = [x[x.rindex("@") + 1 :] for x in emails]

    # creates df of domains and counts
    df = pd.DataFrame(email_domains, columns=["domains"]).value_counts().to_frame().reset_index()

    df = df.rename(columns={"count": "occurrences"})

    # changes the name of the organization if under a certain threshold
    df.loc[df.occurrences <= num, "domains"] = "Other"

    # groups others together for final counts
    df = (
        df.groupby(by="domains")["occurrences"]
        .sum()
        .reset_index()
        .sort_values(by=["occurrences"], ascending=False)
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
    fig = px.bar(df, x="domains", y="occurrences", color_discrete_sequence=[baby_blue[8]])
    fig.update_xaxes(rangeslider_visible=True, range=[-0.5, 15])
    fig.update_layout(
        xaxis_title="Domains",
        yaxis_title="Contributions",
        bargroupgap=0.1,
        margin_b=40,
        font=dict(size=14),
    )
    fig.update_traces(
        hovertemplate="%{label} <br>Contributions: %{value}<br><extra></extra>",
    )

    return fig
