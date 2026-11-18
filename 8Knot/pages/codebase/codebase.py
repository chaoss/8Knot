from dash import html, dcc
import dash
import dash_bootstrap_components as dbc
import warnings

# import visualization cards
from .visualizations.cntrb_file_heatmap import gc_cntrb_file_heatmap
from .visualizations.contribution_file_heatmap import gc_contribution_file_heatmap
from .visualizations.reviewer_file_heatmap import gc_reviewer_file_heatmap

warnings.filterwarnings("ignore")

dash.register_page(__name__, path="/codebase")

layout = dbc.Container(
    [
        dbc.Row(
            dbc.Col(gc_contribution_file_heatmap, xl=10),
            className="visualization-row",
        ),
        dbc.Row(
            dbc.Col(gc_cntrb_file_heatmap, xl=10),
            className="visualization-row",
        ),
        dbc.Row(
            dbc.Col(gc_reviewer_file_heatmap, xl=10),
            className="visualization-row",
        ),
    ],
    fluid=True,
)
