import dash_bootstrap_components as dbc
from dash import callback
from dash.dependencies import Input, Output
import pandas as pd
import logging
import plotly.express as px
from pages.utils.graph_utils import get_graph_time_values, baby_blue
from queries.contributors_query import contributors_query as ctq
from pages.utils.job_utils import nodata_graph
import time
import app
import pages.utils.preprocessing_utils as preproc_utils
import cache_manager.cache_facade as cf
from components.visualization import VisualizationAIO

PAGE = "contributors"
VIZ_ID = "new-contributor"

gc_new_contributor = VisualizationAIO(
    PAGE,
    VIZ_ID,
    title="New Contributors Over Time",
    graph_info="""
    Visualizes the growth of contributor base by tracking the arrival of novel contributors over time.
    """,
    controls=[
        dbc.Label(
            "Date Interval",
            html_for=f"date-interval-{PAGE}-{VIZ_ID}",
            width={"size": "auto"},
        ),
        dbc.Col(
            dbc.RadioItems(
                id=f"date-interval-{PAGE}-{VIZ_ID}",
                options=[
                    {"label": "Day", "value": "D"},
                    {"label": "Week", "value": "W"},
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
    class_name="dark-card",
    id="new-contributors",
)


@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    [
        Input("repo-choices", "data"),
        Input(f"date-interval-{PAGE}-{VIZ_ID}", "value"),
        Input("bot-switch", "value"),
    ],
    background=True,
)
def new_contributor_graph(repolist, interval, bot_switch):
    # wait for data to asynchronously download and become available.
    cf.wait_for_cache(func_name=ctq.__name__, repolist=repolist)

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
        logging.warning("TOTAL_CONTRIBUTOR_GROWTH_VIZ - NO DATA AVAILABLE")
        return nodata_graph

    # remove bot data
    if bot_switch:
        df = df[~df["cntrb_id"].isin(app.bots_list)]

    # function for all data pre processing
    df, df_contribs = process_data(df, interval)

    fig = create_figure(df, df_contribs, interval)

    logging.warning(f"TOTAL_CONTRIBUTOR_GROWTH_VIZ - END - {time.perf_counter() - start}")
    return fig


def process_data(df, interval):
    # convert to datetime objects with consistent column name
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    # df.rename(columns={"created_at": "created"}, inplace=True)

    # order from beginning of time to most recent
    df = df.sort_values("created_at", axis=0, ascending=True)

    """
        Assume that the cntrb_id values are unique to individual contributors.
        Find the first rank-1 contribution of the contributors, saving the created
        date.
    """

    # one row per contributor: earliest action in the selected data
    df = df.sort_values("created_at", ascending=True).drop_duplicates(subset=["cntrb_id"], keep="first")

    # get all of the unique entries by contributor ID
    df.drop_duplicates(subset=["cntrb_id"], inplace=True)
    df.reset_index(inplace=True)

    # variable to slice on to handle weekly period edge case
    period_slice = None
    if interval == "W":
        # this is to slice the extra period information that comes with the weekly case
        period_slice = 10

    # get the count of new contributors in the desired interval in pandas period format, sort index to order entries
    created_range = pd.to_datetime(df["created_at"]).dt.to_period(interval).value_counts().sort_index()

    # converts to data frame object and creates date column from period values
    df_contribs = created_range.to_frame().reset_index().rename(columns={"created_at": "Date", "count": "contribs"})

    # converts date column to a datetime object, converts to string first to handle period information
    df_contribs["Date"] = pd.to_datetime(df_contribs["Date"].astype(str))

    # correction for year binning -
    # rounded up to next year so this is a simple patch
    if interval == "Y":
        df_contribs["Date"] = df_contribs["Date"].dt.year
    elif interval == "M":
        df_contribs["Date"] = df_contribs["Date"].dt.strftime("%Y-%m")

    return df, df_contribs


def create_figure(df, df_contribs, interval):
    # time values for graph
    x_r, x_name, hover, period = get_graph_time_values(interval)

    fig = px.bar(
        df_contribs,
        x="Date",
        y="contribs",
        range_x=x_r,
        labels={"x": x_name, "y": "Contributors"},
        color_discrete_sequence=[baby_blue[8]],
    )
    fig.update_traces(hovertemplate=hover + "<br>Contributors: %{y}<br>")
    fig.update_xaxes(
        showgrid=True,
        ticklabelmode="period",
        dtick=period,
        rangeslider_yaxis_rangemode="match",
        range=x_r,
    )

    fig.update_layout(
        xaxis_title=x_name,
        yaxis_title="Number of Contributors",
        margin_b=40,
        margin_r=20,
        font=dict(size=14),
    )
    return fig
