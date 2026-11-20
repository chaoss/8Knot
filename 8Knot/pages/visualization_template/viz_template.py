from dash import dcc, callback
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash.dependencies import Input, Output
import pandas as pd
import logging
from dateutil.relativedelta import *  # type: ignore
from pages.utils.graph_utils import get_graph_time_values
from queries.QUERY_NAME import QUERY_NAME as QUERY_INITIALS
import cache_manager.cache_facade as cf
from pages.utils.job_utils import nodata_graph, POLL_INTERVAL_MS
from components.visualization import VisualizationAIO
import time
import app  # pylint: disable=unused-import

"""
NOTE: VARIABLES TO CHANGE:

(1) PAGE
(2) VIZ_ID
(3) gc_VISUALIZATION
(4) TITLE OF VISUALIZATION
(5) CONTEXT OF GRAPH
(6) URL-FRIENDLY-IDENTIFIER
(7) IDs of Dash components
(8) NAME_OF_VISUALIZATION_graph
(9) COLUMN_WITH_DATETIME
(10) COLUMN_WITH_DATETIME
(11) COLUMN_TO_SORT_BY
(12) Comments before callbacks
(13) QUERY_USED, QUERY_NAME, QUERY_INITIALS

NOTE: Data queried from Augur is a Postgres->Postgres transaction. If the data that resides in cache requires a pre-processing
        step before it can be used in analysis, it will likely reside in 8Knot/8Knot/pages/utils/preprocessing_utils.py, but "your mileage my vary".

NOTE: IMPORTING A VISUALIZATION INTO A PAGE
(1) Include the visualization file in the visualization folder for the respective page
(2) Import the visualization into the page_name.py file using "from .visualizations.visualization_file_name import gc_visualization_name"
(3) Add the card into new row on the page

NOTE: ADDITIONAL DASH COMPONENTS FOR USER GRAPH CUSTOMIZATIONS

If you add Dash components (ie dbc.Input, dbc.RadioItems, dcc.DatePickerRange...) the ids, html_for, and targets should be in the
following format: f"component-identifier-{PAGE}-{VIZ_ID}"

NOTE: If you change or add a new query, you need to do "docker system prune -af" before building again

NOTE: If you use an alert or take code from a visualization that uses one, make sure to update returns accordingly in the NAME_OF_VISUALIZATION_graph

For more information, check out the new_vis_guidance.md
"""


# TODO: Remove unused imports and edit strings and variables in all CAPS
# TODO: Remove comments specific for the template

PAGE = "page-name"  # EDIT FOR CURRENT PAGE
VIZ_ID = "shortname-of-viz"  # UNIQUE IDENTIFIER FOR VIZUALIZATION


gc_VISUALIZATION = VisualizationAIO(
    PAGE,
    VIZ_ID,
    title="TITLE OF VISUALIZATION",
    graph_info="""
        CONTEXT OF GRAPH
    """,
    controls=[
        dbc.Row(
            [
                dbc.Label(
                    "Date Interval:",
                    html_for=f"date-radio-{PAGE}-{VIZ_ID}",
                    width="auto",
                ),
                dbc.Col(
                    [
                        dbc.RadioItems(
                            id=f"date-radio-{PAGE}-{VIZ_ID}",
                            options=[
                                {
                                    "label": "Trend",
                                    "value": "D",
                                },  # TREND IF LINE, DAY IF NOT
                                # {"label": "Week","value": "W",}, UNCOMMENT IF APPLICABLE
                                {"label": "Month", "value": "M"},
                                {"label": "Year", "value": "Y"},
                            ],
                            value="M",
                            inline=True,
                        ),
                    ]
                ),
            ],
            align="center",
        ),
        # TODO: ADD IN IF ADDITIONAL PARAMETERS FOR GRAPH, REMOVE IF NOT
        """ format dbc.Inputs, including dbc.Alert if needed
                dbc.Label(
                    "TITLE_OF_ADDITIONAL_PARAMETER:",
                    html_for=f"component-identifier-{PAGE}-{VIZ_ID}",
                    width={"size": "auto"},
                ),
                dbc.Col(
                    dbc.Input(
                        id=f"component-identifier-{PAGE}-{VIZ_ID}",
                        type="number",
                        min=1,
                        max=120,
                        step=1,
                        value=7,
                    ),
                    className="me-2",
                    width=2,
                ),
                dbc.Alert(
                    children="Please ensure that 'PARAMETER' is less than 'PARAMETER'",
                    id=f"component-identifier-{PAGE}-{VIZ_ID}",
                    dismissable=True,
                    fade=False,
                    is_open=False,
                    color="warning",
                ),
        """
        """ format for dcc.DatePickerRange:
                dbc.Col(
                    dcc.DatePickerRange(
                        id=f"component-identifier-{PAGE}-{VIZ_ID}",
                        min_date_allowed=dt.date(2005, 1, 1),
                        max_date_allowed=dt.date.today(),
                        clearable=True,
                    ),
                    width="auto",
                ),

        """,
    ],
    class_name="dark-card",
    id="URL-FRIENDLY-IDENTIFIER",
)


# callback for VIZ TITLE graph.
# This is helpful if you want a dynamic title that includes parameters about the current graph configuration
# for example "Number of contributors in the past N months" (where N is a value the user can set)
# This will take precedence over any static title set above
@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    # Output(f"check-alert-{PAGE}-{VIZ_ID}", "is_open"), USE WITH ADDITIONAL PARAMETERS
    # if additional output is added, change returns accordingly
    [
        Input("repo-choices", "data"),
        Input(f"date-radio-{PAGE}-{VIZ_ID}", "value"),
        # Input("bot-switch", "value"),
        # add additional inputs here
    ],
    background=True,
    interval=POLL_INTERVAL_MS,
)
def NAME_OF_VISUALIZATION_graph(repolist, interval):
    # wait for data to asynchronously download and become available.
    while not_cached := cf.get_uncached(func_name=QUERY_INITIALS.__name__, repolist=repolist):
        logging.warning(f"{VIZ_ID}- WAITING ON DATA TO BECOME AVAILABLE")
        time.sleep(0.5)

    logging.warning(f"{VIZ_ID} - START")
    start = time.perf_counter()

    # GET ALL DATA FROM POSTGRES CACHE
    df = cf.retrieve_from_cache(
        tablename=QUERY_INITIALS.__name__,
        repolist=repolist,
    )

    # test if there is data
    if df.empty:
        logging.warning(f"{VIZ_ID} - NO DATA AVAILABLE")
        return nodata_graph

    # uncomment if bot filter applies to viz
    """
    # remove bot data
    if bot_switch:
        df = df[~df["cntrb_id"].isin(app.bots_list)]
    """

    # function for all data pre processing, COULD HAVE ADDITIONAL INPUTS AND OUTPUTS
    df = process_data(df, interval)

    fig = create_figure(df, interval)

    logging.warning(f"{VIZ_ID} - END - {time.perf_counter() - start}")
    return fig


def process_data(df: pd.DataFrame, interval):
    """Implement your custom data-processing logic in this function.
    The output of this function is the data you intend to create a visualization with,
    requiring no further processing."""

    # convert to datetime objects rather than strings
    # ADD ANY OTHER COLUMNS WITH DATETIME
    df["COLUMN_WITH_DATETIME"] = pd.to_datetime(df["COLUMN_WITH_DATETIME"], utc=True)

    # order values chronologically by COLUMN_TO_SORT_BY date
    df = df.sort_values(by="COLUMN_TO_SORT_BY", axis=0, ascending=True)

    """LOOK AT OTHER VISUALIZATIONS TO SEE IF ANY HAVE A SIMILAR DATA PROCESS"""

    return df


def create_figure(df: pd.DataFrame, interval):
    # time values for graph
    x_r, x_name, hover, period = get_graph_time_values(interval)

    # graph generation
    fig = fig

    """LOOK AT OTHER VISUALIZATIONS TO SEE IF ANY HAVE A SIMILAR GRAPH"""

    return fig
