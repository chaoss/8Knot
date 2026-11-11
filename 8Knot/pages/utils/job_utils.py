import plotly.graph_objects as go
import cache_manager.cache_facade as cf

# ms the browser waits between polls for a graph callback's result; Dash's default is 1000
POLL_INTERVAL_MS = 500

columns = ["1", "2", "3"]

# graph displayed if no data is available
nodata_graph = go.Figure([go.Bar(x=columns, y=[20, 14, 23])])
nodata_graph.update_traces(
    marker_color="rgb(230,230,230)",
    marker_line_color="rgb(200,200,300)",
    marker_line_width=1.5,
    opacity=0.6,
)
nodata_graph.update_layout(
    title={
        "text": "No Available Data",
        "y": 0.9,
        "x": 0.5,
        "xanchor": "center",
        "yanchor": "top",
    },
    font=dict(size=18, color="red"),
)

# graph displayed if a worker fails
timeout_graph = go.Figure([go.Bar(x=columns, y=[20, 14, 23])])
timeout_graph.update_traces(
    marker_color="rgb(230,230,230)",
    marker_line_color="rgb(200,200,300)",
    marker_line_width=1.5,
    opacity=0.6,
)
timeout_graph.update_layout(
    title={
        "text": "No Available Data",
        "y": 0.9,
        "x": 0.5,
        "xanchor": "center",
        "yanchor": "top",
    },
    font=dict(size=18, color="orange"),
)


def get_default_repo_with_data(repo_ids, cache_tablename):
    """
    Find the first repo that has valid cached data.

    Args:
        repo_ids: List of repo IDs to check
        cache_tablename: Name of the cache table to query

    Returns:
        str: The first repo_id (as string) that has cached data, or repo_ids[0] as fallback
    """

    df = cf.retrieve_from_cache(tablename=cache_tablename, repolist=repo_ids)

    if df.empty:
        return str(repo_ids[0])

    # Get set of repo_ids that have data
    repos_with_data = set(df["repo_id"].unique())

    # Return first repo with data (preserving original order)
    for repo_id in repo_ids:
        if repo_id in repos_with_data:
            return str(repo_id)

    return str(repo_ids[0])
