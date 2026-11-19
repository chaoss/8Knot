from dash import html, dcc, callback
import dash
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
from datetime import date, timedelta
import pandas as pd
import logging
import plotly.express as px
from dash.exceptions import PreventUpdate
import time

from pages.utils.job_utils import nodata_graph
from queries.contributor_funnel_query import contributor_engagement_query as ceq
import cache_manager.cache_facade as cf
import app

PAGE = "contributors"
VIZ_ID = "contributor-funnel"

gc_contributor_funnel = dbc.Card(
    [
        dbc.CardBody(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            html.H3(
                                "Contributor Funnel",
                                className="card-title",
                            ),
                        ),
                        dbc.Col(
                            dbc.Button(
                                "About Graph",
                                id=f"popover-target-{PAGE}-{VIZ_ID}-funnel",
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
                            "This funnel chart shows the progression of contributors through different engagement stages, from initial interest to active contribution."
                        ),
                    ],
                    id=f"popover-{PAGE}-{VIZ_ID}-funnel",
                    target=f"popover-target-{PAGE}-{VIZ_ID}-funnel",
                    placement="top",
                    is_open=False,
                ),
                dcc.Loading(
                    dcc.Graph(id=f"{PAGE}-{VIZ_ID}-funnel-graph"),
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
                                    html_for=f"date-picker-{PAGE}-{VIZ_ID}-funnel",
                                    width="auto",
                                ),
                                dbc.Col(
                                    dcc.DatePickerRange(
                                        id=f"date-picker-{PAGE}-{VIZ_ID}-funnel",
                                        min_date_allowed=date(2015, 1, 1),
                                        max_date_allowed=date.today(),
                                        start_date=date.today() - timedelta(days=365),
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

gc_contributor_dropoff = dbc.Card(
    [
        dbc.CardBody(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            html.H3(
                                "Drop-offs Between Stages",
                                className="card-title",
                            ),
                        ),
                        dbc.Col(
                            dbc.Button(
                                "About Graph",
                                id=f"popover-target-{PAGE}-{VIZ_ID}-dropoff",
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
                            "This bar chart shows the number of contributors who drop off between each stage of the contributor funnel."
                        ),
                    ],
                    id=f"popover-{PAGE}-{VIZ_ID}-dropoff",
                    target=f"popover-target-{PAGE}-{VIZ_ID}-dropoff",
                    placement="top",
                    is_open=False,
                ),
                dcc.Loading(
                    dcc.Graph(id=f"{PAGE}-{VIZ_ID}-dropoff-graph"),
                    style={"marginBottom": "1rem"},
                ),
            ],
            style={"padding": "1.5rem"},
        ),
    ],
    className="dark-card",
)

@callback(
    Output(f"popover-{PAGE}-{VIZ_ID}-funnel", "is_open"),
    [Input(f"popover-target-{PAGE}-{VIZ_ID}-funnel", "n_clicks")],
    [State(f"popover-{PAGE}-{VIZ_ID}-funnel", "is_open")],
)
def toggle_funnel_popover(n, is_open):
    if n:
        return not is_open
    return is_open


@callback(
    Output(f"popover-{PAGE}-{VIZ_ID}-dropoff", "is_open"),
    [Input(f"popover-target-{PAGE}-{VIZ_ID}-dropoff", "n_clicks")],
    [State(f"popover-{PAGE}-{VIZ_ID}-dropoff", "is_open")],
)
def toggle_dropoff_popover(n, is_open):
    if n:
        return not is_open
    return is_open


@callback(
    Output(f"{PAGE}-{VIZ_ID}-funnel-graph", "figure"),
    Output(f"{PAGE}-{VIZ_ID}-dropoff-graph", "figure"),
    [
        Input("repo-choices", "data"),
        Input(f"date-picker-{PAGE}-{VIZ_ID}-funnel", "start_date"),
        Input(f"date-picker-{PAGE}-{VIZ_ID}-funnel", "end_date"),
        Input("bot-switch", "value"),
    ],
    background=True,
)
def create_funnel_and_dropoff_charts(repolist, start_date, end_date, bot_switch):
    if not repolist:
        raise PreventUpdate

    func_name = ceq.__name__
    not_cached = cf.get_uncached(func_name=func_name, repolist=repolist)
    if not_cached:
        logging.warning(f"{VIZ_ID}: Engagement data for {len(not_cached)} repos not cached. Dispatching worker.")
        ceq.apply_async(args=[not_cached])
        timeout = 180
        start_time = time.time()
        while time.time() - start_time < timeout:
            if not cf.get_uncached(func_name=func_name, repolist=not_cached):
                break
            time.sleep(2)
        
        if cf.get_uncached(func_name=func_name, repolist=repolist):
            logging.warning(f"{VIZ_ID} - TIMEOUT WAITING FOR DATA")
            return nodata_graph(), nodata_graph()

    logging.warning(f"{VIZ_ID} - START")
    start = time.perf_counter()

    df_engagement = cf.retrieve_from_cache(
        tablename=ceq.__name__,
        repolist=repolist,
    )

    if df_engagement is None or df_engagement.empty:
        logging.warning(f"{VIZ_ID} - NO DATA AVAILABLE")
        return nodata_graph(), nodata_graph()

    # Process data for both funnel and dropoff charts using a single date range
    df_funnel, df_dropoff = process_data(df_engagement, start_date, end_date, bot_switch)

    if df_funnel.empty:
        logging.warning(f"{VIZ_ID} - NO DATA AFTER PROCESSING")
        return nodata_graph(), nodata_graph()

    funnel_fig = create_funnel_figure(df_funnel)
    dropoff_fig = create_dropoff_figure(df_dropoff)
    
    logging.warning(f"{VIZ_ID} - END - {time.perf_counter() - start}")
    return funnel_fig, dropoff_fig


def process_data(df: pd.DataFrame, start_date, end_date, bot_switch):
    """
    Process the raw engagement data to calculate funnel stages.
    Filters contributors based on their first engagement activity within the time range.
    """
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    # Apply bot filtering first
    if bot_switch and "cntrb_id" in df.columns:
        df = df[~df["cntrb_id"].isin(app.bots_list)]
    
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    # 'All Contributors' is the total number of unique contributors before date filtering
    all_contributors_count = df['cntrb_id'].nunique()

    # Filter for contributors whose first basic engagement occurred within the time range
    df_filtered = df
    if start_date and end_date:
        start_dt = pd.to_datetime(start_date, utc=True)
        end_dt = pd.to_datetime(end_date, utc=True)

        date_mask = pd.Series(False, index=df.index)
        activity_cols = ['d1_first_issue_created_at', 'd1_first_pr_opened_at', 'd1_first_pr_commented_at']

        for col in activity_cols:
            if col in df.columns:
                col_dt = pd.to_datetime(df[col], utc=True, errors='coerce')
                date_mask |= (col_dt >= start_dt) & (col_dt <= end_dt)
        
        df_filtered = df[date_mask]

    # 'Basic Engagement' are contributors from the time-filtered set
    basic_contributors_count = df_filtered['cntrb_id'].nunique()

    # 'Deep Engagement' are contributors from the basic group who meet deep engagement criteria
    deep_mask = (
        (df_filtered['d2_has_merged_pr'] == True) |
        (df_filtered['d2_created_many_issues'] == True) |
        (df_filtered['d2_total_comments'] >= 5) |
        (df_filtered['d2_has_pr_with_many_commits'] == True) |
        (df_filtered['d2_commented_on_multiple_prs'] == True)
    )
    deep_contributors_count = df_filtered[deep_mask]['cntrb_id'].nunique() if not df_filtered.empty else 0

    stages = ["All Contributors", "Basic Engagement", "Deep Engagement"]
    values = [all_contributors_count, basic_contributors_count, deep_contributors_count]
    
    df_funnel = pd.DataFrame({
        'Stage': stages,
        'Count': values
    })

    # Calculate drop-offs based on the funnel values
    dropoff_stages = []
    dropoff_counts = []
    for i in range(len(values) - 1):
        dropoff_stages.append(f"{stages[i]} → {stages[i+1]}")
        dropoff_counts.append(values[i] - values[i+1])

    df_dropoff = pd.DataFrame({
        'Transition': dropoff_stages,
        'Drop-off Count': dropoff_counts
    })

    return df_funnel, df_dropoff


def create_funnel_figure(df_funnel: pd.DataFrame):
    """Create the funnel chart figure."""
    funnel_fig = px.funnel(
        df_funnel,
        x='Count',
        y='Stage',
        labels={'Count': 'Number of Contributors'}
    )
    funnel_fig.update_layout(
        margin=dict(l=40, r=40, t=40, b=40),
        font=dict(size=14)
    )
    return funnel_fig


def create_dropoff_figure(df_dropoff: pd.DataFrame):
    """Create the drop-off bar chart figure."""
    dropoff_fig = px.bar(
        df_dropoff,
        x='Drop-off Count',
        y='Transition',
        orientation='h',
        text='Drop-off Count',
    )
    dropoff_fig.update_layout(
        yaxis_title=None,
        xaxis_title="Number of Dropped Contributors",
        margin=dict(l=40, r=40, t=40, b=40),
        font=dict(size=14)
    )
    dropoff_fig.update_traces(textposition='outside')
    return dropoff_fig
