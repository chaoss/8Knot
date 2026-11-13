import dash_bootstrap_components as dbc
from dash import callback
from dash.dependencies import Input, Output
import pandas as pd
import logging
import plotly.express as px
from pages.utils.graph_utils import get_graph_time_values, baby_blue
from pages.utils.job_utils import nodata_graph
from queries.contributors_query import contributors_query as ctq
import time
import app
import pages.utils.preprocessing_utils as preproc_utils
import cache_manager.cache_facade as cf
from components.visualization import VisualizationAIO

PAGE = "contributors"
VIZ_ID = "contrib-types-over-time"

gc_contributors_over_time = VisualizationAIO(
    PAGE,
    VIZ_ID,
    title="Contributor Types Over Time",
    graph_info="""
    Visualizes the per-quarter consistency of contributors.\n
    Partitions quarterly population of contributors based on whether they make\n
    'Required Contributions' or more contributions.
    Please read definition of 'Contributor Consistency' on Info page.
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
                max=15,
                step=1,
                value=4,
                size="sm",
                style={"width": "80px"},
                className="dark-input",
            ),
            className="me-2",
            width=2,
        ),
        dbc.Label(
            "Date Interval:",
            html_for=f"date-interval-{PAGE}-{VIZ_ID}",
            width={"size": "auto"},
        ),
        dbc.Col(
            dbc.RadioItems(
                id=f"date-interval-{PAGE}-{VIZ_ID}",
                options=[
                    {
                        "label": "Week",
                        "value": "W",
                    },
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
    id="contributor-types",
)


@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    [
        Input("repo-choices", "data"),
        Input(f"contributions-required-{PAGE}-{VIZ_ID}", "value"),
        Input(f"date-interval-{PAGE}-{VIZ_ID}", "value"),
        Input("bot-switch", "value"),
    ],
    background=True,
)
def create_contrib_over_time_graph(repolist, contribs, interval, bot_switch):
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
        logging.warning("PULL REQUESTS OVER TIME - NO DATA AVAILABLE")
        return nodata_graph

    # remove bot data
    if bot_switch:
        df = df[~df["cntrb_id"].isin(app.bots_list)]

    # function for all data pre processing
    df_drive_repeat = process_data(df, interval, contribs)

    fig = create_figure(df_drive_repeat, interval)

    logging.warning(f"CONTRIBUTIONS_OVER_TIME_VIZ - END - {time.perf_counter() - start}")
    return fig


def process_data(df, interval, contribs):
    # convert to datetime objects with consistent column name
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    # df.rename(columns={"created_at": "created"}, inplace=True)

    # remove null contrib ids
    df.dropna(inplace=True)

    # repeat contributors: >= contribs actions in at least one repo (same partition as rank in explorer_contributor_actions)
    action_counts = df.groupby(["cntrb_id"], sort=False).size()
    contributors = action_counts[action_counts >= contribs].index.get_level_values("cntrb_id").unique().tolist()

    # dfs for drive by and repeat contributors
    df_drive_temp = df.loc[~df["cntrb_id"].isin(contributors)]
    df_repeat_temp = df.loc[df["cntrb_id"].isin(contributors)]

    # order values chronologically by creation date
    df = df.sort_values(by="created_at", axis=0, ascending=True)

    # variable to slice on to handle weekly period edge case
    period_slice = None
    if interval == "W":
        # this is to slice the extra period information that comes with the weekly case
        period_slice = 10

    # create empty df for empty case
    df_drive = pd.DataFrame(columns=["Date", "Drive"])
    df_drive["Drive"] = df_drive.Drive.astype("int64")

    # fill df only if there is data
    if not df_drive_temp.empty:
        # df for drive by contributros in time interval
        df_drive = (
            # disable and re-enable formatter
            # fmt: off
            df_drive_temp.groupby(by=df_drive_temp.created_at.dt.to_period(interval))["cntrb_id"]
            # fmt: on
            .nunique()
            .reset_index()
            .rename(columns={"cntrb_id": "Drive", "created_at": "Date"})
        )
        df_drive["Date"] = pd.to_datetime(df_drive["Date"].astype(str).str[:period_slice])

    # create empty df for empty case
    df_repeat = pd.DataFrame(columns=["Date", "Repeat"])
    df_repeat["Repeat"] = df_repeat.Repeat.astype("int64")

    # fill df only if there is data
    if not df_repeat_temp.empty:
        # df for repeat contributors in time interval
        df_repeat = (
            # disable and re-enable formatter
            # fmt: off
            df_repeat_temp.groupby(by=df_repeat_temp.created_at.dt.to_period(interval))["cntrb_id"]
            # fmt: on
            .nunique()
            .reset_index()
            .rename(columns={"cntrb_id": "Repeat", "created_at": "Date"})
        )
        df_repeat["Date"] = pd.to_datetime(df_repeat["Date"].astype(str).str[:period_slice])

    # A single df created for plotting merged and closed as stacked bar chart
    df_drive_repeat = pd.merge(df_drive, df_repeat, on="Date", how="outer")

    # formating for graph generation
    if interval == "M":
        df_drive_repeat["Date"] = df_drive_repeat["Date"].dt.strftime("%Y-%m-01")
    elif interval == "Y":
        df_drive_repeat["Date"] = df_drive_repeat["Date"].dt.strftime("%Y-01-01")

    return df_drive_repeat


def create_figure(df_drive_repeat, interval):
    # time values for graph
    x_r, x_name, hover, period = get_graph_time_values(interval)

    fig = px.bar(
        df_drive_repeat,
        x="Date",
        y=["Repeat", "Drive"],
        labels={"x": x_name, "y": "Contributors"},
        color_discrete_sequence=[baby_blue[6], baby_blue[8]],
    )
    fig.update_traces(
        hovertemplate=hover + "<br>Contributors: %{y}<br><extra></extra>",
    )
    fig.update_xaxes(
        showgrid=True,
        ticklabelmode="period",
        dtick=period,
        rangeslider_yaxis_rangemode="match",
        range=x_r,
    )
    fig.update_layout(
        xaxis_title=x_name,
        legend_title_text="Type",
        yaxis_title="Number of Contributors",
        margin_b=40,
        font=dict(size=14),
    )

    return fig
