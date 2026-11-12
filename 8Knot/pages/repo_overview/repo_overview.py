from dash import html, dcc, callback
from dash.dependencies import Input, Output, State
import dash
import dash_bootstrap_components as dbc
import warnings
import dash_mantine_components as dmc
from app import augur

# import visualization cards
from .visualizations.code_languages import gc_code_language
from .visualizations.package_version import gc_package_version
from .visualizations.ossf_scorecard import gc_ossf_scorecard
from .visualizations.repo_general_info import gc_repo_general_info

warnings.filterwarnings("ignore")

dash.register_page(__name__, path="/repo_overview")

layout = dbc.Container(
    [
        html.H1("Search Bar Populated Analysis", style={"text-align": "center", "marginBottom": "1%"}),
        dbc.Row(
            dbc.Col(gc_code_language, xl=10),
            className="visualization-row",
        ),
        dbc.Row(
            dbc.Col(gc_package_version, xl=10),
            className="visualization-row",
        ),
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.H1("Per Repo Analysis:"),
                    ],
                    width=3,
                    id="per-repo-analysis",
                ),
                dbc.Col(
                    [
                        dmc.Select(
                            id="repo-info-selection",
                            placeholder="Repo for info section",
                            searchable=True,
                            clearable=True,
                        ),
                    ],
                    width=3,
                ),
            ],
            justify="center",
            align="center",
            style={"marginBottom": "1%"},
        ),
        dbc.Row(
            [
                dbc.Col(gc_ossf_scorecard, width=6),
                dbc.Col(gc_repo_general_info, width=6),
            ],
            className="visualization-row",
        ),
    ],
    fluid=True,
)


# callback for populating repo drop down
@callback(
    [
        Output("repo-info-selection", "data"),
        Output("repo-info-selection", "value"),
    ],
    [Input("repo-choices", "data")],
)
def repo_dropdown(repo_ids):
    # array to hold repo_id and git url pairing for dropdown
    data_array = []
    for repo_id, label in zip(repo_ids, augur.repo_ids_to_git(repo_ids)):
        entry = {"value": str(repo_id), "label": label}
        data_array.append(entry)
    return data_array, str(repo_ids[0])
