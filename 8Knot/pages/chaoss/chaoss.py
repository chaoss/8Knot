from dash import html, dcc
import dash
import dash_bootstrap_components as dbc
import warnings

# import visualization cards
from .visualizations.project_velocity import gc_project_velocity
from .visualizations.contrib_importance_pie import gc_contrib_importance_pie
from .visualizations.contributor_radar import gc_contributor_radar

warnings.filterwarnings("ignore")

dash.register_page(__name__, path="/chaoss")

layout = dbc.Container(
    [
        dbc.Row(
            dbc.Col(gc_contrib_importance_pie, xl=10),
            className="visualization-row",
        ),
        dbc.Row(
            dbc.Col(gc_project_velocity, xl=10),
            className="visualization-row",
        ),
        dbc.Row(
            [
                dbc.Col(gc_contributor_radar, width=6),
            ],
            align="center",
            style={"marginBottom": ".5%"},
        ),
    ],
    fluid=True,
)
