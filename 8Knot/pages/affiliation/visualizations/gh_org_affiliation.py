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
from rapidfuzz import fuzz
import app
import cache_manager.cache_facade as cf
from components.visualization import VisualizationAIO

PAGE = "affiliation"
VIZ_ID = "gh-org-affiliation"

gc_gh_org_affiliation = VisualizationAIO(
    PAGE,
    VIZ_ID,
    title="Organization Affiliation by GitHub Account Info",
    graph_info="""
        Visualizes GitHub account institution affiliation.\n
        Many individuals don't report an affiliated institution, but\n
        this count may be considered an absolute lower-bound on affiliation.
    """,
    controls=[
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
                max=50,
                step=1,
                value=5,
                size="sm",
                className="dark-input",
            ),
            className="me-2",
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
    id="gh-org-affiliation",
)


# callback for Organization Affiliation by Github Account Info graph
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
def gh_org_affiliation_graph(repolist, num, start_date, end_date, bot_switch):
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
    df = process_data(df, num, start_date, end_date)

    fig = create_figure(df)

    logging.warning(f"{VIZ_ID} - END - {time.perf_counter() - start}")
    return fig


def process_data(df: pd.DataFrame, num, start_date, end_date):
    """Implement your custom data-processing logic in this function.
    The output of this function is the data you intend to create a visualization with,
    requiring no further processing."""

    # convert to datetime objects rather than strings
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)

    # order values chronologically by COLUMN_TO_SORT_BY date
    df = df.sort_values(by="created_at", axis=0, ascending=True)

    # filter values based on date picker
    if start_date is not None:
        df = df[df.created_at >= start_date]
    if end_date is not None:
        df = df[df.created_at <= end_date]

    # intital count of same company name in github profile
    result = df.cntrb_company.value_counts(dropna=False)

    # reset format for df work
    df = result.to_frame()
    df["company_name"] = df.index
    df = df.reset_index()
    df["company_name"] = df["company_name"].astype(str)
    df = df.rename(columns={"cntrb_company": "orginal_name", "count": "contribution_count"})

    # applies fuzzy matching comparing all rows to each other
    df["match"] = df.apply(lambda row: fuzzy_match(df, row["company_name"]), axis=1)

    # changes company name to match other fuzzy matches
    for x in range(0, len(df)):
        # gets match values for the current row
        matches = df.iloc[x]["match"]
        for y in matches:
            # for each match, change the name to its match and clear out match column as
            # it will unnecessarily reapply changes
            df.loc[y, "company_name"] = df.iloc[x]["company_name"]
            df.loc[y, "match"] = ""

    # groups all same name company affiliation and sums the contributions
    df = (
        df.groupby(by="company_name")["contribution_count"]
        .sum()
        .reset_index()
        .sort_values(by=["contribution_count"])
        .reset_index(drop=True)
    )

    # changes the name of the company if under a certain threshold
    df.loc[df["contribution_count"] <= num, "company_name"] = "Other"

    # groups others together for final counts
    df = (
        df.groupby(by="company_name")["contribution_count"]
        .sum()
        .reset_index()
        .sort_values(by=["contribution_count"])
        .reset_index(drop=True)
    )

    return df


def fuzzy_match(df, name):
    """
    This function compares each row to all of the other values in the company_name column and
    outputs a list on if there is a fuzzy match between the different rows. This gives the values
    necessary for the loop to change the company name if there is a match. 70 is the match value
    threshold for the partial ratio to be considered a match
    """
    matches = df.apply(lambda row: (fuzz.partial_ratio(row["company_name"], name, score_cutoff=70) >= 70), axis=1)
    return [i for i, x in enumerate(matches) if x]


def create_figure(df: pd.DataFrame):
    # graph generation
    fig = px.pie(
        df,
        names="company_name",
        values="contribution_count",
        color_discrete_sequence=baby_blue,
    )
    fig.update_traces(
        textposition="inside",
        textinfo="percent+label",
        hovertemplate="%{label} <br>Contributions: %{value}<br><extra></extra>",
    )

    return fig
