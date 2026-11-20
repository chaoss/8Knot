from dash import html, dcc, callback
import dash
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import pandas as pd
import logging
from dateutil.relativedelta import *  # type: ignore
import plotly.express as px
from pages.utils.graph_utils import baby_blue
from queries.package_version_query import package_version_query as pvq
from pages.utils.job_utils import nodata_graph, POLL_INTERVAL_MS
import time
import datetime as dt
import cache_manager.cache_facade as cf
from components.visualization import VisualizationAIO

PAGE = "repo_info"
VIZ_ID = "package-version"

gc_package_version = VisualizationAIO(
    PAGE,
    VIZ_ID,
    title="Package Version Updates",
    graph_info="""
        Shows the version freshness of each packaged dependency in the repository.
        Dependencies are grouped by how outdated they are: up to date, less than 6 months
        behind, between 6 months and 1 year behind, or more than 1 year behind.
    """,
    controls=[],
    class_name="dark-card",
    id="package-version",
)


# callback for package version updates graph
@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    [
        Input("repo-choices", "data"),
    ],
    background=True,
    interval=POLL_INTERVAL_MS,
)
def package_version_graph(repolist):
    # wait for data to asynchronously download and become available.
    while not_cached := cf.get_uncached(func_name=pvq.__name__, repolist=repolist):
        logging.warning(f"{VIZ_ID}- WAITING ON DATA TO BECOME AVAILABLE")
        time.sleep(0.5)

    start = time.perf_counter()
    logging.warning(f"{VIZ_ID}- START")

    # GET ALL DATA FROM POSTGRES CACHE
    df = cf.retrieve_from_cache(
        tablename=pvq.__name__,
        repolist=repolist,
    )

    # test if there is data
    if df.empty:
        logging.warning(f"{VIZ_ID} - NO DATA AVAILABLE")
        return nodata_graph

    # count the number of each package grouping
    df = pd.DataFrame(df["dep_age"].value_counts().reset_index())

    # graph generation
    fig = px.pie(df, names="dep_age", values="count", color_discrete_sequence=baby_blue)
    fig.update_traces(
        textposition="inside",
        textinfo="percent+label",
        hovertemplate="%{label} <br>Packages: %{value}<br><extra></extra>",
    )

    # add legend title
    fig["layout"]["legend_title"] = "Date Range"

    logging.warning(f"{VIZ_ID} - END - {time.perf_counter() - start}")
    return fig
