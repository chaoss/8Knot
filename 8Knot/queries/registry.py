"""Data queries shared by browser dispatch and standalone cache warming.

Importing this registry must not initialize the Dash app or register callbacks.
"""

from queries.issues_query import issues_query
from queries.commits_query import commits_query
from queries.contributors_query import contributors_query
from queries.prs_query import prs_query
from queries.issue_assignee_query import issue_assignee_query
from queries.pr_assignee_query import pr_assignee_query
from queries.pr_response_query import pr_response_query
from queries.cntrb_per_file_query import cntrb_per_file_query
from queries.repo_files_query import repo_files_query
from queries.pr_files_query import pr_file_query
from queries.repo_languages_query import repo_languages_query
from queries.package_version_query import package_version_query
from queries.repo_releases_query import repo_releases_query
from queries.ossf_score_query import ossf_score_query
from queries.repo_info_query import repo_info_query
from queries.affiliation_query import affiliation_query

# Keep the slow affiliation JOIN last so faster queries can start first.
QUERIES = [
    issues_query,
    commits_query,
    contributors_query,
    prs_query,
    issue_assignee_query,
    pr_assignee_query,
    pr_response_query,
    cntrb_per_file_query,
    repo_files_query,
    pr_file_query,
    repo_languages_query,
    package_version_query,
    repo_releases_query,
    ossf_score_query,
    repo_info_query,
    affiliation_query,
]
