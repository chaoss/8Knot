"""
Layout components for the main application structure.

This file contains reusable UI components that make up the main application shell,
including the sidebar, main content area, and navigation elements.
"""

from dash import html, dcc
import dash
import dash_bootstrap_components as dbc
from components.dropdown_nav_item import DropdownNavItemAIO
from components.nav_item import NavItemAIO

# This will be imported from the main layout file
search_bar = None


def create_main_content_area():
    """Create the main content area with loading components and page container."""
    return html.Div(
        id="page-container",
        className="page-container",
        children=[
            dcc.Loading(
                children=[html.Div(id="results-output-container", className="loading-container mb-4")],
                type="dot",
                fullscreen=True,
            ),
            dcc.Loading(
                dbc.Badge(
                    children="Data Loaded",
                    id="data-badge",
                    className="data-badge me-1",
                ),
                type="cube",
            ),
            dash.page_container,
        ],
    )


def create_sidebar_navigation():
    return dbc.Nav(
        children=[
            DropdownNavItemAIO(
                [
                    NavItemAIO(
                        "Code Languages",
                        "/repo_overview#code-languages",
                    ),
                    NavItemAIO(
                        "Package Version",
                        "/repo_overview#package-version",
                    ),
                    NavItemAIO(
                        "Per-Repo Analysis",
                        "/repo_overview#per-repo-analysis",
                    ),
                ],
                "/assets/repo_overview.svg",
                "Repo Overview",
                "/repo_overview",
            ),
            DropdownNavItemAIO(
                [
                    NavItemAIO(
                        "Commits Over Time",
                        "/contributions#commits-over-time",
                    ),
                    NavItemAIO(
                        "PRs Over Time",
                        "/contributions#prs-over-time",
                    ),
                    NavItemAIO(
                        "PR Activity - Staleness",
                        "/contributions#pr-staleness",
                    ),
                    NavItemAIO(
                        "Self Merge Rate",
                        "/contributions#self-merge-rate",
                    ),
                    NavItemAIO(
                        "PR Time to First Response",
                        "/contributions#pr-first-response",
                    ),
                    NavItemAIO(
                        "PR Conversation Engagement",
                        "/contributions#pr-review-response",
                    ),
                    NavItemAIO(
                        "PR Review Status Counts",
                        "/contributions#pr_assignment",
                    ),
                    NavItemAIO(
                        "Contributor PR Review Assignment",
                        "/contributions#cntrib-pr-assignment",
                    ),
                    NavItemAIO(
                        "Issues Over Time",
                        "/contributions#issues-over-time",
                    ),
                    NavItemAIO(
                        "Issue Activity - Staleness",
                        "/contributions#issue-staleness",
                    ),
                    NavItemAIO(
                        "Issue Assignment Status Counts",
                        "/contributions#issue_assignment",
                    ),
                    NavItemAIO(
                        "Contributor Issue Assignment",
                        "/contributions#cntrib-issue-assignment",
                    ),
                ],
                "/assets/contributions.svg",
                "Contributions",
                "/contributions",
            ),
            DropdownNavItemAIO(
                [
                    NavItemAIO(
                        "Drive-Through Contributors",
                        "/contributors/behavior#drive-throughs",
                    ),
                    NavItemAIO(
                        "First-Time Contributors",
                        "/contributors/behavior#first-time-contributors",
                    ),
                    NavItemAIO(
                        "Engagement Growth",
                        "/contributors/behavior#engagement-growth",
                    ),
                    NavItemAIO(
                        "New Contributors",
                        "/contributors/behavior#new-contributors",
                    ),
                    NavItemAIO(
                        "Contributor Types",
                        "/contributors/behavior#contributor-types",
                    ),
                ],
                "/assets/contributors.svg",
                "Contributor Behavior",
                "/contributors/behavior",
            ),
            DropdownNavItemAIO(
                [
                    NavItemAIO(
                        "Contributor Actions",
                        "/contributors/contribution_types#contributor-actions",
                    ),
                    NavItemAIO(
                        "Contributor Activity Cycle",
                        "/contributors/contribution_types#contributor-activity-cycle",
                    ),
                    NavItemAIO(
                        "Lottery Factor Snapshot",
                        "/contributors/contribution_types#lottery-factor-snapshot",
                    ),
                    NavItemAIO(
                        "Lottery Factor over Time",
                        "/contributors/contribution_types#lottery-factor-time",
                    ),
                ],
                "/assets/contributors.svg",
                "Contributor Types",
                "/contributors/contribution_types",
            ),
            DropdownNavItemAIO(
                [
                    NavItemAIO(
                        "Commits by Domain",
                        "/affiliation#commits-by-domain",
                    ),
                    NavItemAIO(
                        "Unique Domains",
                        "/affiliation#unique-domains",
                    ),
                    NavItemAIO(
                        "Org Activity",
                        "/affiliation#org-activity",
                    ),
                    NavItemAIO(
                        "Org Core Contributors",
                        "/affiliation#org-core-contributors",
                    ),
                    NavItemAIO(
                        "GitHub Org Affiliation",
                        "/affiliation#gh-org-affiliation",
                    ),
                ],
                "/assets/affiliation.svg",
                "Affiliation",
                "/affiliation",
            ),
            DropdownNavItemAIO(
                [
                    NavItemAIO(
                        "Lottery Factor",
                        "/chaoss#lottery-factor",
                    ),
                    NavItemAIO(
                        "Project Velocity",
                        "/chaoss#project-velocity",
                    ),
                ],
                "/assets/chaoss_small.svg",
                "CHAOSS",
                "/chaoss",
            ),
            DropdownNavItemAIO(
                [
                    NavItemAIO(
                        "PR File Heatmap",
                        "/codebase#contribution-file-heatmap",
                    ),
                    NavItemAIO(
                        "Contributor File Heatmap",
                        "/codebase#cntrb-file-heatmap",
                    ),
                    NavItemAIO(
                        "Reviewer File Heatmap",
                        "/codebase#reviewer-file-heatmap",
                    ),
                ],
                "/assets/codebase.svg",
                "Codebase",
                "/codebase",
            ),
        ],
        vertical=True,
    )


def create_sidebar():
    """Create the collapsible sidebar with search and navigation."""
    return dbc.Collapse(
        html.Div(
            [
                html.Div(
                    [
                        search_bar,
                        create_sidebar_navigation(),
                    ],
                    className="sidebar-body",
                ),
            ],
            className="sidebar-container",
        ),
        id="sidebar-collapse",
        is_open=False,
        dimension="width",
    )


def create_main_layout():
    """Create the main application layout container."""
    return html.Div(
        id="main-layout-container",
        className="main-layout-container",
        children=[
            create_sidebar(),
            create_main_content_area(),
        ],
    )


def create_app_stores():
    """Create application-level data stores."""
    return [
        dcc.Store(id="repo-choices", storage_type="session", data=[]),
        dcc.Store(id="job-ids", storage_type="session", data=[]),
        dcc.Store(id="user-group-loading-signal", data="", storage_type="memory"),
        # no-op output sink for the clientside scroll-to-anchor callback
        dcc.Store(id="anchor-scroll-dummy", data=None),
        dcc.Location(id="url"),
    ]


def initialize_components(search_bar_ref):
    """
    Initialize component references from the main layout file.

    Args:
        search_bar_ref: Reference to the search bar component from index_layout.py
                       Used to make the search bar available to sidebar components
    """
    global search_bar
    search_bar = search_bar_ref
