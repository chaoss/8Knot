import os
import datetime as dt

import pandas as pd
import plotly.express as px

# list of graph color hex
color_seq = [
    "#B5B682",  # sage
    "#c0bc5d",  # citron (yellow-ish)
    "#6C8975",  # reseda green
    "#D9AE8E",  # buff (pale pink)
    "#FFBF51",  # xanthous (orange-ish)
    "#C7A5A5",  # rosy brown
]

# Baby Blue color scale for graph gradients
baby_blue = [
    "#DFF0FB",  # Baby Blue 100 - very light
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

# Sequential color scale for heatmaps (light -> dark blue with yellow accent, matches app theme)
# Progression: very light blue -> medium light -> main blue -> dark blue -> yellow accent
heatmap_color_scale = [
    baby_blue[0],  # Very light blue (#DFF0FB) - low values
    baby_blue[2],  # Medium light blue (#76C5EF)
    baby_blue[4],  # Main baby blue (#199AD6) - mid values
    baby_blue[6],  # Dark blue (#0F5880)
    baby_blue[8],  # Yellow accent (#F7B009) - high values/emphasis
]


def create_heatmap_figure(
    df: pd.DataFrame,
    color_label: str,
    x_label: str = "Time",
    y_label: str = "Directory Entries",
):
    """Build heatmap layout shared by codebase heatmaps. Cell NaNs are OK (missing months)."""

    fig = px.imshow(
        df,
        labels=dict(x=x_label, y=y_label, color=color_label),
        color_continuous_scale=heatmap_color_scale,
    )
    fig.update_layout(
        height=700,
        font=dict(size=14),
        xaxis_title=x_label,
        yaxis_title=y_label,
        yaxis=dict(tickmode="linear", side="right"),
        coloraxis_colorbar_x=-0.15,
        coloraxis=dict(
            colorbar=dict(
                tickfont=dict(color="white"),
                title=dict(font=dict(color="white")),
            )
        ),
    )
    return fig


def get_graph_time_values(interval):
    """
    Utility needed in page visualizations-
    when the user inputs an 'interval', they're wanting to view
    data in some time window. This function converts that
    'interval' value to the necessary Plotly figure update values.

    Args:
    -----
        interval (str | int): How long between time bins, user selected.

    Returns:
    --------
        x_r ([str]): Time-bin strings.
        x_name (str): Name of bin-duration.
        hover (str): String-structure for graph to print on mouse-hover.
        period (str): How long selected time bin is.
    """
    today = dt.date.today()
    x_r = None
    x_name = "Year"
    hover = "Year: %{x|%Y}"
    period = "M12"  # dtick values must be in millisecond or M format

    # graph input values based on date interval selection
    if interval == 86400000 or interval == "D":  # if statement for days
        x_r = [str(today - dt.timedelta(weeks=4)), str(today)]
        x_name = "Day"
        hover = "Day: %{x|%b %d, %Y}"
        period = 86400000 * 2
    elif interval == 604800000 or interval == "W":  # if statmement for weeks
        x_r = [str(today - dt.timedelta(weeks=30)), str(today)]
        x_name = "Week"
        hover = "Week: %{x|%b %d, %Y}"
        period = 1814400000
    elif interval == "M" or interval == "M1":  # if statement for months
        x_r = [str(today - dt.timedelta(weeks=104)), str(today)]
        x_name = "Month"
        hover = "Month: %{x|%b %Y}"
        period = "M3"
    elif interval == "M3":  # if statement for quarter
        x_r = [str(today - dt.timedelta(weeks=312)), str(today)]
        x_name = "Quarter"
        hover = "Quarter: %{x}"
        period = "M6"
    elif interval == "M6":  # if statement for half a year
        x_r = [str(today - dt.timedelta(weeks=624)), str(today)]
        x_name = "Semiannual"
        hover = "Semiannual: %{x}"
        period = "M12"
    else:
        period = "M12"

    return x_r, x_name, hover, period


def contributor_label():
    """Column and display name to use when labelling contributors in a graph.

    8Knot anonymizes contributors by default, labelling them with a truncated
    contributor UUID. That is the right default for a public deployment, but a
    deployment tracking only public repositories often wants the GitHub
    username, which is already public information and much easier to read.

    Set EIGHTKNOT_CONTRIBUTOR_LABEL=login to opt in. Anything else, including
    unset, keeps the existing anonymized behavior. The graphs that call this are
    background callbacks, so the variable has to reach worker-callback -- setting
    it only on app-server does nothing.

    Returns a (column, display name) pair.
    """
    if os.getenv("EIGHTKNOT_CONTRIBUTOR_LABEL", "id").lower() == "login":
        return "login", "Contributor"
    return "cntrb_id", "Contributor ID"
