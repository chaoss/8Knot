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
from queries.repo_languages_query import repo_languages_query as rlq
from pages.utils.job_utils import nodata_graph
import time
import datetime as dt
import cache_manager.cache_facade as cf
from components.visualization import VisualizationAIO

PAGE = "repo_info"
VIZ_ID = "code-languages"

gc_code_language = VisualizationAIO(
    PAGE,
    VIZ_ID,
    graph_info="""
        Visualizes the percent of files or lines of code by language.
    """,
    controls=[
        dbc.Row(
            [
                dbc.Label(
                    "Graph View:",
                    html_for=f"graph-view-{PAGE}-{VIZ_ID}",
                    width={"size": "auto"},
                ),
                dbc.Col(
                    dbc.RadioItems(
                        id=f"graph-view-{PAGE}-{VIZ_ID}",
                        options=[
                            {
                                "label": "Files",
                                "value": "file",
                            },
                            {
                                "label": "Lines of Code",
                                "value": "line",
                            },
                        ],
                        value="file",
                        inline=True,
                        className="custom-radio-buttons",
                    ),
                    className="me-2",
                    width=4,
                ),
            ],
            align="center",
            justify="start",
        ),
    ],
    class_name="dark-card",
    id="code-languages",
)


# callback for dynamically changing the graph title
@callback(
    Output(f"graph-title-{PAGE}-{VIZ_ID}", "children"),
    Input(f"graph-view-{PAGE}-{VIZ_ID}", "value"),
)
def graph_title(view):
    title = ""
    if view == "file":
        title = "File Language by File"
    else:
        title = "File Language by Line"
    return title


# callback for code languages graph
@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    [
        Input("repo-choices", "data"),
        Input(f"graph-view-{PAGE}-{VIZ_ID}", "value"),
    ],
    background=True,
)
def code_languages_graph(repolist, view):
    # wait for data to asynchronously download and become available.
    cf.wait_for_cache(func_name=rlq.__name__, repolist=repolist)

    start = time.perf_counter()
    logging.warning(f"{VIZ_ID}- START")

    # GET ALL DATA FROM POSTGRES CACHE
    df = cf.retrieve_from_cache(
        tablename=rlq.__name__,
        repolist=repolist,
    )

    # test if there is data
    if df.empty:
        logging.warning(f"{VIZ_ID} - NO DATA AVAILABLE")
        return nodata_graph

    # function for all data pre processing
    df = process_data(df)

    fig = create_figure(df, view)

    logging.warning(f"{VIZ_ID} - END - {time.perf_counter() - start}")
    return fig


def process_data(df: pd.DataFrame):

    # SVG files give one line of code per file
    df.loc[df["programming_language"] == "SVG", "code_lines"] = df["files"]

    # require a language to have atleast .1 % of total lines to be shown, if not grouped into other
    min_lines = df["code_lines"].sum() / 1000
    df.loc[df.code_lines <= min_lines, "programming_language"] = "Other"
    df = df[["programming_language", "code_lines", "files"]].groupby("programming_language").sum().reset_index()

    # order by descending file number and reset format
    df = df.sort_values(by="files", axis=0, ascending=False).reset_index()
    df.drop("index", axis=1, inplace=True)

    # calculate percentages
    df["Code %"] = (df["code_lines"] / df["code_lines"].sum()) * 100
    df["Files %"] = (df["files"] / df["files"].sum()) * 100

    return df


def create_figure(df: pd.DataFrame, view):

    value = "files"
    if view == "line":
        value = "code_lines"

    # graph generation
    fig = px.pie(df, names="programming_language", values=value, color_discrete_sequence=baby_blue)
    fig.update_traces(
        textposition="inside",
        textinfo="percent+label",
        hovertemplate="%{label} <br>Amount: %{value}<br><extra></extra>",
    )

    return fig
