from dash import html, dcc, callback
import dash
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
from datetime import date, timedelta, datetime
import pandas as pd
import logging
import plotly.express as px
from dash.exceptions import PreventUpdate
import time

import app
from cache_manager import cache_facade as cf
from pages.utils.job_utils import nodata_graph
from queries.contributors_query import contributors_query as cnq

PAGE = "contributors"
VIZ_ID = "contributor-radar"

gc_contributor_radar = dbc.Card(
    [
        dbc.CardBody(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            html.H3(
                                "Contributor Activity Radar",
                                className="card-title",
                            ),
                        ),
                        dbc.Col(
                            dbc.Button(
                                "About Graph",
                                id=f"popover-target-{PAGE}-{VIZ_ID}",
                                color="outline-secondary",
                                size="sm",
                                className="about-graph-button",
                            ),
                            width="auto",
                        ),
                    ],
                    align="center",
                    justify="between",
                    className="mb-3",
                ),
                dbc.Popover(
                    [
                        dbc.PopoverHeader("Graph Info:"),
                        dbc.PopoverBody(
                            "This radar chart shows the number of unique contributors performing different key activities within the selected time range."
                        ),
                    ],
                    id=f"popover-{PAGE}-{VIZ_ID}",
                    target=f"popover-target-{PAGE}-{VIZ_ID}",
                    placement="top",
                    is_open=False,
                ),
                dcc.Loading(
                    dcc.Graph(id=f"{PAGE}-{VIZ_ID}", figure=nodata_graph),
                    style={"marginBottom": "1rem"},
                ),
                html.Hr(  # Divider between graph and controls
                    style={
                        "borderColor": "#909090",
                        "margin": "1.5rem -1.5rem",
                        "width": "calc(100% + 3rem)",
                    }
                ),
                dbc.Form(
                    [
                        dbc.Row(
                            [
                                dbc.Label(
                                    "Select Time Range:",
                                    html_for=f"date-picker-{PAGE}-{VIZ_ID}",
                                    width="auto",
                                ),
                                dbc.Col(
                                    dcc.DatePickerRange(
                                        id=f"date-picker-{PAGE}-{VIZ_ID}",
                                        min_date_allowed=date(2015, 1, 1),
                                        max_date_allowed=date.today(),
                                        start_date=date.today() - timedelta(days=180),
                                        end_date=date.today(),
                                        display_format='YYYY-MM-DD',
                                        className="dark-date-picker",
                                    ),
                                    width=5,
                                ),
                            ],
                            align="center",
                        ),
                    ]
                ),
            ],
            style={"padding": "1.5rem"},
        ),
    ],
    className="dark-card",
)

# callback for graph info popover
@callback(
    Output(f"popover-{PAGE}-{VIZ_ID}", "is_open"),
    [Input(f"popover-target-{PAGE}-{VIZ_ID}", "n_clicks")],
    [State(f"popover-{PAGE}-{VIZ_ID}", "is_open")],
)
def toggle_popover(n, is_open):
    if n:
        return not is_open
    return is_open


# callback for contributor radar graph
@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    [
        Input(f"date-picker-{PAGE}-{VIZ_ID}", "start_date"),
        Input(f"date-picker-{PAGE}-{VIZ_ID}", "end_date"),
        Input("repo-choices", "data"),
        Input("bot-switch", "value"),
    ],
    background=True,
)
def generate_radar_chart_from_data(start_date, end_date, repolist, bot_switch):
    """
    This callback fetches raw contributor actions, applies the date filter in Pandas,
    aggregates the data, and then creates the radar chart.
    """
    logging.warning(f"--- {VIZ_ID} CALLBACK TRIGGERED ---")
    if not repolist or not start_date or not end_date:
        raise PreventUpdate

    # wait for data to asynchronously download and become available.
    func_name = cnq.__name__
    not_cached = cf.get_uncached(func_name=func_name, repolist=repolist)
    if not_cached:
        logging.warning(f"{VIZ_ID}: Raw action data for {len(not_cached)} repos not cached. Dispatching worker.")
        cnq.apply_async(args=[not_cached])
        timeout = 180
        start_time = time.time()
        while time.time() - start_time < timeout:
            if not cf.get_uncached(func_name=func_name, repolist=not_cached):
                break
            time.sleep(2)

    logging.warning(f"{VIZ_ID} - START")
    start = time.perf_counter()

    # GET ALL DATA FROM POSTGRES CACHE
    df = cf.retrieve_from_cache(tablename=func_name, repolist=repolist)

    # test if there is data
    if df.empty:
        logging.warning(f"{VIZ_ID} - NO DATA AVAILABLE")
        return nodata_graph()

    # function for all data pre processing and figure creation
    fig = process_data_and_create_figure(df, start_date, end_date, bot_switch)

    logging.warning(f"{VIZ_ID} - END - {time.perf_counter() - start}")
    return fig


def process_data_and_create_figure(df: pd.DataFrame, start_date, end_date, bot_switch):
    """
    Process the raw contributor data, filter by date range and bot switch,
    and create the radar chart figure.
    """
    # Convert to datetime and filter by date range
    df['created_at'] = pd.to_datetime(df['created_at'], utc=True)
    start_date_dt = pd.to_datetime(start_date, utc=True)
    end_date_dt = pd.to_datetime(end_date, utc=True)
    df = df[(df['created_at'] >= start_date_dt) & (df['created_at'] <= end_date_dt)]

    # Aggregate actions for each contributor
    df_agg = df.groupby(['repo_id', 'cntrb_id', 'login']).agg(
        created_issue=('action', lambda x: 1 if 'issue_opened' in x.values else 0),
        opened_pr=('action', lambda x: 1 if 'pull_request_open' in x.values else 0),
        pr_commented=('action', lambda x: 1 if 'pull_request_comment' in x.values else 0),
        committed=('action', lambda x: 1 if 'commit' in x.values else 0),
        pr_merged=('action', lambda x: 1 if 'pull_request_merged' in x.values else 0),
    ).reset_index()

    # remove bot data if switch is on
    if bot_switch and "cntrb_id" in df_agg.columns:
        df_agg = df_agg[~df_agg["cntrb_id"].isin(app.bots_list)]

    # return no data graph if df is empty after processing
    if df_agg.empty:
        logging.warning(f"{VIZ_ID} - NO DATA AVAILABLE AFTER PROCESSING")
        return nodata_graph()

    # Create the radar chart figure
    activity_metrics = {
        "Issue Creators": df_agg[df_agg["created_issue"] == 1]["login"].nunique(),
        "PR Openers": df_agg[df_agg["opened_pr"] == 1]["login"].nunique(),
        "PR Commenters": df_agg[df_agg["pr_commented"] == 1]["login"].nunique(),
        "PR Mergers": df_agg[df_agg["pr_merged"] == 1]["login"].nunique(),
    }

    radar_df = pd.DataFrame(dict(Count=list(activity_metrics.values()), Activity=list(activity_metrics.keys())))

    fig = px.line_polar(
        radar_df, r='Count', theta='Activity', line_close=True, markers=True,
        title=" "
    )
    fig.update_traces(fill='toself')
    fig.update_layout(
        margin=dict(l=60, r=60, t=60, b=40),
        font=dict(size=14)
    )

    return fig
