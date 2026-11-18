from dash import callback
from dash.dependencies import Input, Output
import pandas as pd
import logging
import plotly.express as px
from pages.utils.graph_utils import baby_blue
from queries.contributors_query import contributors_query as ctq
import time
from pages.utils.job_utils import nodata_graph, POLL_INTERVAL_MS
import app
import pages.utils.preprocessing_utils as preproc_utils
import cache_manager.cache_facade as cf
from components.visualization import VisualizationAIO

PAGE = "contributors"
VIZ_ID = "first-time-contribution"

gc_first_time_contributions = VisualizationAIO(
    PAGE,
    VIZ_ID,
    title="First Time Contributors Per Quarter",
    graph_info="""
    Visualizes the arrival of net-new contributors to a project\n
    and differentiates them by their first in-project action.
    """,
    class_name="dark-card",
    id="first-time-contributors",
)


@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    [
        Input("repo-choices", "data"),
        Input("bot-switch", "value"),
    ],
    background=True,
    interval=POLL_INTERVAL_MS,
)
def create_first_time_contributors_graph(repolist, bot_switch):
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
        logging.warning("1ST CONTRIBUTIONS - NO DATA AVAILABLE")
        return nodata_graph

    # remove bot data
    if bot_switch:
        df = df[~df["cntrb_id"].isin(app.bots_list)]

    # function for all data pre processing
    df = process_data(df)

    fig = create_figure(df)

    logging.warning(f"1ST_CONTRIBUTIONS_VIZ - END - {time.perf_counter() - start}")
    return fig


def process_data(df):
    # convert to datetime objects with consistent column name
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    # df.rename(columns={"created_at": "created"}, inplace=True)

    # one row per contributor: earliest action in the selected data
    df = df.sort_values("created_at", ascending=True).drop_duplicates(subset=["cntrb_id"], keep="first")

    # reset index to be ready for plotly
    df = df.reset_index()

    return df


def create_figure(df):
    # create plotly express histogram
    fig = px.histogram(df, x="created_at", color="Action", color_discrete_sequence=baby_blue)

    # creates bins with 3 month size and customizes the hover value for the bars
    fig.update_traces(
        xbins_size="M3",
        hovertemplate="Date: %{x}" + "<br>Amount: %{y}",
    )

    # update xaxes to align for the 3 month bin size
    fig.update_xaxes(showgrid=True, ticklabelmode="period", dtick="M3")

    # layout styling
    fig.update_layout(
        xaxis_title="Quarter",
        yaxis_title="Contributions",
        margin_b=40,
        font=dict(size=14),
    )

    return fig
