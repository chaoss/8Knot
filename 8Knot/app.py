"""
README -- Organization of Callback Functions

In an effort to compartmentalize our development where possible, all callbacks directly relating
to pages in our application are in their own files.

For instance, this file contains the layout logic for the index page of our app-
this page serves all other paths by providing the searchbar, page routing faculties,
and data storage objects that the other pages in our app use.

Having laid out the HTML-like organization of this page, we write the callbacks for this page in
the neighbor 'app_callbacks.py' file.
"""

import os
import sys
import logging
import dash
import pandas as pd
from sqlalchemy.exc import SQLAlchemyError
import sqlalchemy as salc
import plotly.io as plt_io
import dash_bootstrap_components as dbc
import dash_bootstrap_templates as dbt
from db_manager.collectoss_manager import CollectOSSManager
import _login
from _celery import celery_app, celery_manager
import _bots as bots

logging.basicConfig(format="%(asctime)s %(levelname)-8s %(message)s", level=logging.INFO)


"""CREATE DATABASE ACCESS OBJECT AND CACHE SEARCH OPTIONS"""
use_oauth = os.getenv("AUGUR_LOGIN_ENABLED", "False") == "True"
try:
    # create CollectOSS manager object. init fails if
    # necessary environment variables aren't available.
    augur = CollectOSSManager(handles_oauth=use_oauth)

    # create engine. fails if test connection to DB fails.
    engine = augur.get_engine()

except KeyError:
    sys.exit(1)
except SQLAlchemyError:
    sys.exit(1)

# grab list of projects and orgs from Augur database.
augur.multiselect_startup()


"""IMPORT AFTER GLOBAL VARIABLES SET"""
import pages.index.index_callbacks as index_callbacks
import pages.landing.landing_callbacks as landing_callbacks

# Import testing utilities for enhanced error detection in CI
if os.getenv("DEBUG_8KNOT", "False") == "True":
    import testing_utils

    testing_utils.log_service_status()


"""SET STYLING FOR APPLICATION"""
dbt.load_figure_template(["sandstone", "minty", "slate"])

# stylesheet with the .dbc class, this is a complement to the dash bootstrap templates, credit AnnMarieW
dbc_css = "https://cdn.jsdelivr.net/gh/AnnMarieW/dash-bootstrap-templates/dbc.min.css"

# making custom plotly template with custom colors on top of the slate design template
plt_io.templates["custom_dark"] = plt_io.templates["slate"]
plt_io.templates["custom_dark"]["layout"]["colorway"] = [
    "#F0F9FF",  # Baby Blue 100 - very light
    "#A8D9F5",  # Baby Blue 200 - light
    "#76C5EF",  # Baby Blue 300 - medium light
    "#3FB0E9",  # Baby Blue 400 - light blue
    "#199AD6",  # Baby Blue 500 - main baby blue
    "#147AAE",  # Baby Blue 600 - medium dark
    "#0F5880",  # Baby Blue 700 - dark
    "#0369A1",  # Baby Blue 800 - very dark
    "#F7B009",  # Yellow 500 - main yellow
    "#FEDF89",  # Yellow 200 - light yellow
    "#B54708",  # Yellow 700 - dark yellow
]

# Match plot backgrounds, fonts, and legend styling to the dark shell/card theme
_tpl = plt_io.templates["custom_dark"]
_tpl["layout"].update(
    {
        "paper_bgcolor": "#292929",  # matches card background
        "plot_bgcolor": "#292929",
        "font": {"color": "white"},
        "title": {"x": 0, "font": {"color": "white"}},
        "legend": {"font": {"color": "white"}, "bgcolor": "rgba(0,0,0,0)"},
        "hoverlabel": {"bgcolor": "#404040", "font": {"color": "white"}},
        "xaxis": {
            "gridcolor": "#404040",
            "zerolinecolor": "#404040",
            "linecolor": "#606060",
            "tickfont": {"color": "white"},
            "title": {"font": {"color": "white"}},
        },
        "yaxis": {
            "gridcolor": "#404040",
            "zerolinecolor": "#404040",
            "linecolor": "#606060",
            "tickfont": {"color": "white"},
            "title": {"font": {"color": "white"}},
        },
        "margin": {"l": 40, "r": 20, "t": 40, "b": 40},
    }
)

plt_io.templates.default = "custom_dark"


"""CREATE APPLICATION"""
app = dash.Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[dbc.themes.SLATE, dbc_css, dbc.icons.FONT_AWESOME],
    suppress_callback_exceptions=True,
    background_callback_manager=celery_manager,
)

"""CONFIGURE FLASK-LOGIN"""
server = app.server
server = _login.configure_server_login(server)

"""HEALTH CHECK ENDPOINT"""


@server.route("/health")
def health_check():
    """Simple health check endpoint for CI/CD testing"""
    try:
        # Test database connection
        with engine.connect() as conn:
            conn.execute(salc.text("SELECT 1"))

        return {"status": "healthy", "database": "connected", "timestamp": str(pd.Timestamp.now())}, 200
    except Exception as e:
        logging.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "error": str(e), "timestamp": str(pd.Timestamp.now())}, 500


"""DASH PAGES LAYOUT"""
# layout of the app stored in the app_layout file, must be imported after the app is initiated
from pages.index.index_layout import layout
import dash_mantine_components as dmc

app.layout = dmc.MantineProvider(
    layout,
    forceColorScheme="dark",
)

"""DASH STARTUP PARAMETERS"""

if os.getenv("DEBUG_8KNOT", "False") == "True":
    app.enable_dev_tools(dev_tools_ui=True, dev_tools_hot_reload=True, debug=True)

"""GITHUB BOTS LIST"""
bots_list = bots.get_bots_list()
