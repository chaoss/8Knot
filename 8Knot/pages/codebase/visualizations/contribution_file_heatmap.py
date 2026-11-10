from dash import callback
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash.dependencies import Input, Output
import pandas as pd
import logging
from dateutil.relativedelta import *  # type: ignore
from pages.utils.graph_utils import create_heatmap_figure
from queries.prs_query import prs_query as prq
from queries.pr_files_query import pr_file_query as prfq
from queries.repo_files_query import repo_files_query as rfq
from app import augur as collectoss
from pages.utils.job_utils import nodata_graph, get_default_repo_with_data
import time
import cache_manager.cache_facade as cf
from components.visualization import VisualizationAIO

PAGE = "codebase"
VIZ_ID = "contribution-file-heatmap"

gc_contribution_file_heatmap = VisualizationAIO(
    PAGE,
    VIZ_ID,
    title="Contribution File Heatmap",
    graph_info="""
    This visualization analyzes the activity of the open or merged pull requests to sub-sections
    (files or folders) of a repository.
    """,
    controls=[
        dbc.Row(
            [
                dbc.Label(
                    "Select Repository:",
                    html_for=f"repo-{PAGE}-{VIZ_ID}",
                    width="auto",
                ),
                dbc.Col(
                    [
                        dmc.Select(
                            id=f"repo-{PAGE}-{VIZ_ID}",
                            placeholder="Repo for Heatmap",
                            classNames={"values": "dmc-multiselect-custom"},
                            searchable=True,
                            clearable=True,
                        ),
                    ],
                    className="me-2",
                ),
                dbc.Label(
                    "Select Directory:",
                    html_for=f"patterns-{PAGE}-{VIZ_ID}",
                    width="auto",
                ),
                dbc.Col(
                    [
                        dmc.Select(
                            id=f"directory-{PAGE}-{VIZ_ID}",
                            classNames={"values": "dmc-multiselect-custom"},
                            searchable=True,
                            clearable=False,
                        ),
                    ],
                    className="me-2",
                ),
            ],
            align="center",
        ),
        dbc.Row(
            [
                dbc.Label(
                    "Graph View:",
                    html_for=f"graph-view-{PAGE}-{VIZ_ID}",
                    width="auto",
                ),
                dbc.Col(
                    [
                        dbc.RadioItems(
                            id=f"graph-view-{PAGE}-{VIZ_ID}",
                            options=[
                                {"label": "PR Opened", "value": "created_at"},
                                {"label": "PR Merged", "value": "merged_at"},
                            ],
                            value="created_at",
                            inline=True,
                        ),
                    ]
                ),
            ],
            align="center",
        ),
    ],
    class_name="dark-card",
    id="contribution-file-heatmap",
)


# callback for populating repo drop down
@callback(
    [
        Output(f"repo-{PAGE}-{VIZ_ID}", "data"),
        Output(f"repo-{PAGE}-{VIZ_ID}", "value"),
    ],
    [Input("repo-choices", "data")],
)
def repo_dropdown(repo_ids):
    # array to hold repo_id and git url pairing for dropdown
    data_array = []
    for repo_id, label in zip(repo_ids, collectoss.repo_ids_to_git(repo_ids)):
        entry = {"value": str(repo_id), "label": label}
        data_array.append(entry)

    # Select first repo with valid cached data as default
    default = get_default_repo_with_data(repo_ids, rfq.__name__)

    return data_array, default


# callback for populating directory drop down
@callback(
    [
        Output(f"directory-{PAGE}-{VIZ_ID}", "data"),
        Output(f"directory-{PAGE}-{VIZ_ID}", "value"),
    ],
    [Input(f"repo-{PAGE}-{VIZ_ID}", "value")],
    background=True,
)
def directory_dropdown(repo_id):
    # Convert to int since Mantine dropdown returns strings
    repo_id = int(repo_id)

    # wait for data to asynchronously download and become available.
    logging.warning(f"DIRECTORY DROPDOWN - WAITING FOR DATA TO LOAD")
    while not_cached := cf.get_uncached(func_name=rfq.__name__, repolist=[repo_id]):
        logging.warning(f"DIRECTORY DROPDOWN - WAITING ON DATA TO BECOME AVAILABLE")
        time.sleep(0.5)

    logging.warning(f"DIRECTORY DROPDOWN - RETRIEVING FROM CACHE")
    df = cf.retrieve_from_cache(
        tablename=rfq.__name__,
        repolist=[repo_id],
    )

    logging.warning(f"DIRECTORY DROPDOWN - CACHE READ")

    # test if there is data
    if df.empty:
        logging.warning(f"{VIZ_ID} DROPDOWN- NO DATA AVAILABLE")
        return ["Top Level Directory"], "Top Level Directory"

    # strings to hold the values for each column (always the same for every row of this query)
    repo_name = df["repo_name"].iloc[0]
    repo_path = df["repo_path"].iloc[0]
    repo_id = str(df["repo_id"].iloc[0])

    # pattern found in each file path, used to slice to get only the root file path
    path_slice = repo_id + "-" + repo_path + "/" + repo_name + "/"
    df["file_path"] = df["file_path"].str.rsplit(path_slice, n=1).str[1]

    # drop unneccessary columns not needed after preprocessing steps
    df = df.reset_index()
    df.drop(
        ["index", "repo_id", "repo_name", "repo_path", "rl_analysis_date"],
        axis=1,
        inplace=True,
    )

    # split file path by directory
    df = df.join(df["file_path"].str.split("/", expand=True))

    # take all of the files, split on the last instance of a / to get directories and top level files
    directories = df["file_path"].str.rsplit("/", n=1).str[0].tolist()
    directories = list(set(directories))

    # get all of the file names to filter out of the directory set
    top_level_files = df["file_name"][df[1].isnull()].tolist()
    # applies another rsplit to make sure directories that only have folders are included
    folder_only_directories = [x.rsplit("/", 1)[0] for x in directories]
    directories = list(set(directories + folder_only_directories))

    # sort alphabetically
    directories = sorted(directories)

    # add top level directory to the list of directories
    directories.insert(0, "Top Level Directory")

    return directories, "Top Level Directory"


# callback for contributor file heatmap graph
@callback(
    Output(f"{PAGE}-{VIZ_ID}", "figure"),
    [
        Input(f"repo-{PAGE}-{VIZ_ID}", "value"),
        Input(f"directory-{PAGE}-{VIZ_ID}", "value"),
        Input(f"graph-view-{PAGE}-{VIZ_ID}", "value"),
    ],
    background=True,
)
def cntrb_file_heatmap_graph(repo_id, directory, graph_view):
    start = time.perf_counter()
    logging.warning(f"{VIZ_ID}- START")

    # Convert to int since Mantine dropdown returns strings
    repo_id = int(repo_id)

    # get dataframes of data from cache
    df_file, df_file_pr, df_pr = multi_query_helper([repo_id])

    # test if there is data
    if df_file.empty or df_file_pr.empty or df_pr.empty:
        logging.warning(f"{VIZ_ID} - NO DATA AVAILABLE")
        return nodata_graph

    # function for all data pre processing
    df = process_data(df_file, df_file_pr, df_pr, directory, graph_view)

    # if there are no pull request on a directory plot no data graph
    if df.empty:
        return nodata_graph

    fig = create_figure(df, graph_view)

    logging.warning(f"{VIZ_ID} - END - {time.perf_counter() - start}")
    return fig


def multi_query_helper(repos):
    """
    For cntrb_file_heatmap_graph-
    hack to put all of the cache-retrieval
    in the same place temporarily
    """

    # wait for data to asynchronously download and become available.
    while not_cached := cf.get_uncached(func_name=rfq.__name__, repolist=repos):
        logging.warning(f"CONTRIBUTION FILE HEATMAP - WAITING ON DATA TO BECOME AVAILABLE")
        time.sleep(0.5)

    # wait for data to asynchronously download and become available.
    while not_cached := cf.get_uncached(func_name=prfq.__name__, repolist=repos):
        logging.warning(f"CONTRIBUTION FILE HEATMAP - WAITING ON DATA TO BECOME AVAILABLE")
        time.sleep(0.5)

    # wait for data to asynchronously download and become available.
    while not_cached := cf.get_uncached(func_name=prq.__name__, repolist=repos):
        logging.warning(f"CONTRIBUTION FILE HEATMAP - WAITING ON DATA TO BECOME AVAILABLE")
        time.sleep(0.5)

    # GET ALL DATA FROM POSTGRES CACHE
    df_file = cf.retrieve_from_cache(
        tablename=rfq.__name__,
        repolist=repos,
    )
    df_file_pr = cf.retrieve_from_cache(
        tablename=prfq.__name__,
        repolist=repos,
    )
    df_pr = cf.retrieve_from_cache(
        tablename=prq.__name__,
        repolist=repos,
    )

    return df_file, df_file_pr, df_pr


def process_data(
    df_file: pd.DataFrame,
    df_file_pr: pd.DataFrame,
    df_pr: pd.DataFrame,
    directory,
    graph_view,
):
    """
    Processing steps

        1 - Cleans up file data to only include current files and relate files in the repository to the prs that impact them.
        2 - For a given level in the directory tree, aggregate the list of prs for sub-directories and for individual files at the level.
        3 - For each pr, identify their open and merged.
        4 - Transforms dataframe where columns are months with counts of pr open/merge dates in that month and the rows are the file/subdirectory
    """

    df_file = df_file_clean(df_file, df_file_pr)

    df_dynamic_directory = pr_per_directory_value(directory, df_file)

    # work around for using functions, will clean later
    if df_dynamic_directory.empty:
        return df_dynamic_directory

    df_dynamic_directory = pr_to_dates(df_pr, df_dynamic_directory, graph_view)

    final = file_pr_activity_by_month(df_dynamic_directory, df_pr, graph_view)

    return final


def create_figure(df: pd.DataFrame, graph_view):
    color_label = "PRs Merged" if graph_view == "merged_at" else "PRs Opened"
    return create_heatmap_figure(df, color_label=color_label)


def df_file_clean(df_file: pd.DataFrame, df_file_pr: pd.DataFrame):
    """
    This function cleans the df_file data and combines it with the related pull request ids

    Args:
    -----
        df_file : Pandas Dataframe
            Dataframe with the output of the repo_files_query

        df_file_prs : Pandas Dataframe
            Dataframe with the output of the pr_file_query

    Returns:
    --------
        df_file: df with file and pull_request_ids of prs with that file in it
    """
    # strings to hold the values for each column (always the same for every row of this query)
    repo_name = df_file["repo_name"].iloc[0]
    repo_path = df_file["repo_path"].iloc[0]
    repo_id = str(df_file["repo_id"].iloc[0])

    # pattern found in each file path, used to slice to get only the root file path
    path_slice = repo_id + "-" + repo_path + "/" + repo_name + "/"
    df_file["file_path"] = df_file["file_path"].str.rsplit(path_slice, n=1).str[1]

    # drop unneccessary columns not needed after preprocessing steps
    df_file = df_file.reset_index()
    df_file.drop(["index", "repo_name", "repo_path", "rl_analysis_date"], axis=1, inplace=True)

    # split file path by directory
    df_file = df_file.join(df_file["file_path"].str.split("/", expand=True))

    # drop unnecessary columns
    df_file.drop(["repo_id"], axis=1, inplace=True)
    df_file_pr.drop(["repo_id"], axis=1, inplace=True)

    # create column with list of prs per file path
    df_file_pr = df_file_pr.groupby("file_path")["pull_request"].apply(list)

    # Left join on df_files to only get the files that are currently in the repository
    # and the prs that included edits on the file
    df_file = pd.merge(df_file, df_file_pr, on="file_path", how="left")

    return df_file


def pr_per_directory_value(directory, df_file):
    """
    This function gets the files in the specified directory, groups together any files in
    subdirectories, and creates a list of pull_request_ids that touched those files

    Args:
    -----
        directory : string
            Output from the directory drop down

        df_file : Pandas Dataframe
            Dataframe with file and related pull_request_id information

    Returns:
    --------
        df_dynamic_directory: df with the file and subdirectories and their prs pull_request_ids
    """
    # determine directory level to use in later step
    level = directory.count("/")
    if directory == "Top Level Directory":
        level = -1
        directory = ""

    # get all of the files in the directory or nested in folders in the directory
    df_dynamic_directory = df_file[df_file["file_path"].str.startswith(directory)]

    # test if there is any pull requests in the directory
    if df_dynamic_directory.pull_request.isnull().all():
        return pd.DataFrame()

    # get one level up from the directory level
    group_column = level + 1

    # Groupby the level above the selected directory for all files nested in folders are together.
    # For each, create a list of all of the contributors who have contributed
    df_dynamic_directory = (
        df_dynamic_directory.groupby(group_column)["pull_request"]
        .sum()
        .reset_index()
        .rename(columns={group_column: "directory_value"})
    )

    # reformat 0 to "" for later processing
    df_dynamic_directory.loc[df_dynamic_directory.pull_request == 0, "pull_request"] = ""

    # Set of pull_request to confirm there are no duplicate pull requests
    df_dynamic_directory["pull_request"] = df_dynamic_directory.apply(
        lambda row: set(row.pull_request),
        axis=1,
    )
    return df_dynamic_directory


def pr_to_dates(df_pr: pd.DataFrame, df_dynamic_directory: pd.DataFrame, graph_view):
    """
    This function creates a df with the files and the the open and merge dates of the prs that
    touch each file or subdirectory.

    Args:
    -----
        df_pr : Pandas Dataframe
            Dataframe with pull request data

        df_dynamic_directory : Pandas Dataframe
            Dataframe with file and related pull_request_id information

    Returns:
    --------
        df_dynamic_directory: df with the file and subdirectories and the dates of open and merge dates
        of the prs that touch each file or subdirectory.
    """

    # date reformating
    df_pr["created_at"] = pd.to_datetime(df_pr["created_at"], utc=True)
    df_pr["merged_at"] = pd.to_datetime(df_pr["merged_at"], utc=True)

    # drop unneccessary columns not needed after preprocessing steps
    df_pr.drop(
        ["repo_id", "repo_name", "pr_src_number", "cntrb_id", "closed_at"],
        axis=1,
        inplace=True,
    )

    # dictionaries of pull_requests and their open and merge dates
    pr_open = df_pr.set_index("pull_request_id")["created_at"].to_dict()
    pr_merged = df_pr.set_index("pull_request_id")["merged_at"].to_dict()

    # get list of pr created and merged dates for each pr
    df_dynamic_directory["created_at"], df_dynamic_directory["merged_at"] = zip(
        *df_dynamic_directory.apply(
            lambda row: [
                [pr_open[x] for x in row.pull_request],
                [pr_merged[x] for x in row.pull_request if (not pd.isnull(pr_merged[x]))],
            ],
            axis=1,
        )
    )

    # reformat into each row being a directory value and a date of one of the pull request dates
    df_dynamic_directory = df_dynamic_directory.explode(graph_view)

    return df_dynamic_directory


def file_pr_activity_by_month(df_dynamic_directory: pd.DataFrame, df_pr: pd.DataFrame, graph_view):
    """
    This function transforms the df_dynamic_directory to be counts of open or merged prs by month.

    Args:
    -----
        df_dynamic_directory : Pandas Dataframe
            Dataframe with file and related reviewer_id information

        df_pr : Pandas Dataframe
            Dataframe with pull request data

    Returns:
    --------
        df_final: df with files and subdirectories as rows and the months as columns
    """

    # get files that have no pull requests and remove from set to prevent errors in grouper function
    no_contribs = df_dynamic_directory["directory_value"][df_dynamic_directory[graph_view].isnull()].tolist()

    df_dynamic_directory = df_dynamic_directory[~df_dynamic_directory[graph_view].isnull()]

    """Creates df with a column for each month between start and end date. This will be used to confirm that
    there will be a column for every month even if there is no pull request date in it. This greatly
    improves the heatmap ploting"""

    # dates based on creation and closed dates so it represents the length of the project
    min_date = df_pr.created_at.min()
    max_date = max(df_pr["created_at"].max(), df_pr["merged_at"].max())
    dates = pd.date_range(start=min_date, end=max_date, freq="M", inclusive="both")
    df_fill = dates.to_frame(index=False, name=graph_view)

    # combine df with data and filler dates together
    final = pd.concat([df_dynamic_directory, df_fill], axis=0)
    final["directory_value"] = final["directory_value"].astype(str)

    # grouping dates by every month and counting the number of pr opened or merged with the last activity at that date
    final = final.groupby(pd.Grouper(key=graph_view, freq="1M"))["directory_value"].value_counts().unstack(0)

    # removing the None row that was used for column formating if exists
    if "nan" in final.index:
        final.drop("nan", inplace=True)

    # add back the files that had no pull requests
    for files in no_contribs:
        final.loc[files] = None

    return final
