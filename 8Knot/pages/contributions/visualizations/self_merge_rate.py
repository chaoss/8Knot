import dash_bootstrap_components as dbc
from dash import callback
from dash.dependencies import Input, Output
import plotly.graph_objects as go
import pandas as pd
import logging
import time
import cache_manager.cache_facade as cf
from components.visualization import VisualizationAIO
from queries.prs_query import prs_query as prq
from pages.utils.graph_utils import get_graph_time_values
from pages.utils.job_utils import nodata_graph, POLL_INTERVAL_MS

PAGE = "contributions"
VIZ_ID = "self-merge"

gc_self_merge = VisualizationAIO(
    PAGE,
    VIZ_ID,
    graph_info="""
    Tracks merged pull requests where the author and the merger are the same contributor.\n
    Switch graph view to see total vs. self-merged counts over time, or the self-merge rate as a percentage.\n
    CHAOSS metric definition: https://chaoss.community/kb/metric-self-merge-rates/
    """,
    controls=[
        dbc.Label(
            "Date Interval:",
            html_for=f"date-interval-{PAGE}-{VIZ_ID}",
            width="auto",
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
                        "label": "Counts",
                        "value": "counts",
                    },
                    {
                        "label": "Rate (%)",
                        "value": "rate",
                    },
                ],
                value="counts",
                inline=True,
                className="custom-radio-buttons",
            ),
        ),
    ],
    class_name="dark-card",
    id="self-merge-rate",
)


@callback(
    Output(f"graph-title-{PAGE}-{VIZ_ID}", "children"),
    Input(f"graph-view-{PAGE}-{VIZ_ID}", "value"),
)
def graph_title(view):
    if view == "rate":
        return "Self-Merge Pull Requests Rate (%)"
    return "Self Merge Pull Requests Rates"


@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    [
        Input("repo-choices", "data"),
        Input(f"date-interval-{PAGE}-{VIZ_ID}", "value"),
        Input(f"graph-view-{PAGE}-{VIZ_ID}", "value"),
    ],
    background=True,
    interval=POLL_INTERVAL_MS,
)
def self_merge_graph(repolist, interval, view):
    start = time.perf_counter()
    logging.warning("SELF MERGE - START")

    df = _load_merged_prs(repolist, "SELF MERGE")

    if df.empty:
        logging.warning("SELF MERGE - NO DATA AVAILABLE")
        return nodata_graph

    df_plot = process_data(df, interval)

    if view == "rate":
        fig = create_rate_figure(df_plot, interval)
    else:
        fig = create_counts_figure(df_plot, interval)

    logging.warning(f"SELF MERGE - END - {time.perf_counter() - start}")
    return fig


def _load_merged_prs(repolist, viz_name):
    """Shared data loading for self-merge callback."""
    while not_cached := cf.get_uncached(func_name=prq.__name__, repolist=repolist):
        logging.warning(f"{viz_name} - WAITING ON DATA TO BECOME AVAILABLE")
        time.sleep(0.5)

    df = cf.retrieve_from_cache(
        tablename=prq.__name__,
        repolist=repolist,
    )

    if not df.empty:
        df = df[df["merged_at"].notna() & (df["merged_at"] != "")]

    return df


def process_data(df: pd.DataFrame, interval):
    df["merged_at"] = pd.to_datetime(df["merged_at"], utc=True)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)

    # self-merge: author == merger (with safe handling of nulls)
    df["cntrb_id"] = df["cntrb_id"].astype(str)
    df["merger_cntrb_id"] = df["merger_cntrb_id"].fillna("").astype(str)
    df["is_self_merge"] = (df["cntrb_id"] == df["merger_cntrb_id"]) & (df["merger_cntrb_id"] != "")

    # period slice for date formatting
    period_slice = 10 if interval == "W" else (4 if interval == "Y" else 7)

    # counts per period by merged_at
    merged_range = df["merged_at"].dt.to_period(interval).value_counts().sort_index()
    df_merged = merged_range.to_frame().reset_index().rename(columns={"merged_at": "Date", "count": "total_merged"})
    df_merged["Date"] = pd.to_datetime(df_merged["Date"].astype(str).str[:period_slice])

    self_merge_range = df[df["is_self_merge"]]["merged_at"].dt.to_period(interval).value_counts().sort_index()
    df_self = self_merge_range.to_frame().reset_index().rename(columns={"merged_at": "Date", "count": "self_merged"})
    df_self["Date"] = pd.to_datetime(df_self["Date"].astype(str).str[:period_slice])

    df_plot = df_merged.merge(df_self, on="Date", how="outer").fillna(0)
    df_plot["self_merged"] = df_plot["self_merged"].astype(int)
    df_plot["rate_pct"] = (df_plot["self_merged"] / df_plot["total_merged"].replace(0, float("nan")) * 100).round(1)

    if interval == "M":
        df_plot["Date_str"] = pd.to_datetime(df_plot["Date"]).dt.strftime("%Y-%m-01")
    elif interval == "Y":
        df_plot["Date_str"] = pd.to_datetime(df_plot["Date"]).dt.strftime("%Y-01-01")
    else:
        df_plot["Date_str"] = pd.to_datetime(df_plot["Date"]).dt.strftime("%Y-%m-%d")

    df_plot = df_plot.sort_values("Date").reset_index(drop=True)

    return df_plot


def create_counts_figure(df_plot: pd.DataFrame, interval):
    x_r, x_name, hover, period = get_graph_time_values(interval)

    fig = go.Figure(
        [
            go.Scatter(
                name="Merged (total)",
                x=df_plot["Date_str"],
                y=df_plot["total_merged"],
                mode="lines",
                showlegend=True,
                hovertemplate="Merged (total): %{y}<br>%{x|%b %d, %Y} <extra></extra>",
            ),
            go.Scatter(
                name="Self-merged",
                x=df_plot["Date_str"],
                y=df_plot["self_merged"],
                mode="lines",
                showlegend=True,
                hovertemplate="Self-merged: %{y}<br>%{x|%b %d, %Y} <extra></extra>",
            ),
        ]
    )

    fig.update_xaxes(showgrid=True, ticklabelmode="period", dtick=period, range=x_r, title_text=x_name)
    fig.update_yaxes(title_text="Number of PRs")
    fig.update_layout(font=dict(size=14), margin_b=40)

    return fig


def create_rate_figure(df_plot: pd.DataFrame, interval):
    x_r, x_name, hover, period = get_graph_time_values(interval)

    fig = go.Figure(
        go.Scatter(
            x=df_plot["Date_str"],
            y=df_plot["rate_pct"],
            mode="lines",
            name="Self-merge rate (%)",
            marker=dict(size=6),
            hovertemplate="%{x}<br>Rate: %{y:.1f}%<extra></extra>",
        )
    )

    fig.update_xaxes(showgrid=True, ticklabelmode="period", dtick=period, range=x_r, title_text=x_name)
    fig.update_yaxes(title_text="Self-merge rate (%)")
    fig.update_layout(font=dict(size=14), margin_b=40)

    return fig
