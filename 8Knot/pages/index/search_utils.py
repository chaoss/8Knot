"""
Search utilities for the 8Knot application.
Provides layout components for the searchbar (search itself runs in postgres-cache).
Uses Dash All-in-One Components pattern for reusable, generic components.

Generic Builders (All-in-One Pattern):
    create_alert: Build any type of alert component
    create_button: Build buttons or nav links

Search-Specific Functions:
    create_search_bar: Complete search bar with all features
    create_bottom_navbar: Bottom navigation with request links
"""

from typing import List, Dict, Optional, Union

# Dash imports for layout components
from dash import html, dcc
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

from metadata import __version__


def create_alert(
    alert_id: str,
    children: Union[str, List],
    color: str = "info",
    dismissable: bool = True,
    fade: bool = True,
    is_open: bool = False,
    icon_class: Optional[str] = None,
    custom_style: Optional[Dict] = None,
    custom_class: str = "",
) -> dbc.Alert:
    """
    Generic alert component builder following Dash All-in-One Components pattern.

    Args:
        alert_id: Unique identifier for the alert
        children: Content of the alert (string or list of components)
        color: Bootstrap color theme (info, warning, danger, success, light, etc.)
        dismissable: Whether the alert can be dismissed
        fade: Whether to use fade animation
        is_open: Initial open state
        icon_class: Optional Font Awesome icon class to prepend
        custom_style: Optional custom styles dictionary
        custom_class: Optional custom CSS class names

    Returns:
        dbc.Alert component configured with provided parameters
    """
    # Prepend icon if provided
    content = children
    if icon_class:
        if isinstance(children, str):
            content = [html.I(className=icon_class), " ", children]
        else:
            content = [html.I(className=icon_class), " "] + (children if isinstance(children, list) else [children])

    return dbc.Alert(
        children=content,
        id=alert_id,
        color=color,
        dismissable=dismissable,
        fade=fade,
        is_open=is_open,
        style=custom_style or {},
        className=custom_class,
    )


def create_button(
    button_id: str,
    content: Union[str, html.I],
    n_clicks: int = 0,
    size: str = "sm",
    color: str = "outline-secondary",
    title: str = "",
    disabled: bool = False,
    custom_style: Optional[Dict] = None,
    custom_class: str = "",
    href: Optional[str] = None,
    external_link: bool = False,
    target: Optional[str] = None,
) -> Union[dbc.Button, dbc.NavLink]:
    """
    Generic button/nav-link component builder following All-in-One pattern.

    Args:
        button_id: Unique identifier for the button
        content: Button content (string or icon component)
        n_clicks: Initial click count
        size: Button size
        color: Bootstrap color theme
        title: Tooltip text
        disabled: Whether button is disabled
        custom_style: Optional custom styles dictionary
        custom_class: Optional custom CSS class names
        href: If provided, creates a NavLink instead of Button
        external_link: Whether link is external (for NavLink)
        target: Link target attribute (for NavLink)

    Returns:
        dbc.Button or dbc.NavLink component based on parameters
    """
    if href:
        return dbc.NavLink(
            content,
            id=button_id,
            disabled=disabled,
            href=href,
            external_link=external_link,
            target=target,
            className=custom_class,
        )

    return dbc.Button(
        content,
        id=button_id,
        n_clicks=n_clicks,
        size=size,
        color=color,
        title=title,
        disabled=disabled,
        style=custom_style or {},
        className=custom_class,
    )


# ===== LAYOUT COMPONENT FUNCTIONS =====


def create_multiselect_styles():
    """
    Create the style configuration for the MultiSelect component.
    Uses CSS variables from color.css and main_layout.css.

    Note: DMC MultiSelect requires inline styles via the 'styles' prop.
    This is a component-specific API, not regular inline styling.

    Returns:
        Dictionary of style configurations
    """
    return {
        "input": {
            "fontSize": "var(--placeholder-font-size)",
            "minHeight": "var(--multiselect-min-height)",
            "height": "auto",
            "padding": "var(--multiselect-padding)",
            "borderRadius": "var(--border-radius-xl)",
            "display": "flex",
            "flexWrap": "wrap",
            "alignItems": "flex-start",
            "backgroundColor": "var(--bg-primary)",
            "borderColor": "var(--border-color-ui)",
            "position": "relative",
            "zIndex": 1,
        },
        "dropdown": {
            "borderRadius": "var(--border-radius-lg)",
            "backgroundColor": "var(--bg-primary)",
            "border": "1px solid var(--border-color-dark)",
        },
        "item": {
            "borderRadius": "var(--border-radius)",
            "margin": "var(--multiselect-item-margin)",
            "color": "var(--color-white)",
        },
        # Inline styles for pending pill color (red by default, turns blue with "searching" class)
        "value": {
            "backgroundColor": "var(--pill-pending-bg)",
            "color": "var(--pill-text-color)",
        },
        "pill": {
            "backgroundColor": "var(--pill-pending-bg)",
            "color": "var(--pill-text-color)",
        },
    }


def create_search_multiselect(initial_option):
    """
    Create the main MultiSelect search component.

    Args:
        initial_option: Initial option dictionary with 'label' and 'value' keys

    Returns:
        dmc.MultiSelect component configured for search
    """
    return dmc.MultiSelect(
        id="projects",
        searchable=True,
        clearable=True,
        nothingFoundMessage="No matching repos/orgs.",
        placeholder="Search",
        variant="filled",
        debounce=100,
        # options are already filtered server-side; see assets/search_filter.js
        filter={"function": "passThroughFilter"},
        # selections stay in `data` so their pills keep labels; don't list them in the dropdown too
        hidePickedOptions=True,
        data=[initial_option],
        value=[initial_option["value"]],
        className="searchbar-dropdown",
        styles=create_multiselect_styles(),
    )


def create_search_input_section(initial_option):
    """
    Create the search input section with MultiSelect and search icon.

    Args:
        initial_option: Initial option dictionary for the MultiSelect

    Returns:
        html.Div containing the search input components
    """
    return html.Div(
        [
            html.Div(
                [
                    create_search_multiselect(initial_option),
                ],
                className="search-input-wrapper",
            ),
            html.Div(
                [
                    dbc.Button(
                        "Search",
                        id="search-button",
                        color="outline-secondary",
                        size="sm",
                        className="about-graph-button",
                    ),
                    create_search_controls(),
                ],
                className="search-button-wrapper",
            ),
            dcc.Store(id="applied-projects", data=[]),
            html.Div(id="selection-error", role="alert"),
            create_alert(
                alert_id="help-alert",
                children='Please ensure that your spelling is correct. \
                    If your selection definitely isn\'t present, please request that \
                    it be loaded using the help button "REPO/ORG Request" \
                    in the bottom right corner of the screen.  \
                    The search is only confirmed when you click the Search button and the pill turns blue.',
                color="info",
            ),
            create_alert(
                alert_id="repo-list-alert",
                children="List of repos",
                color="light",
                custom_class="repo-list-alert",
            ),
        ],
        className="search-input-section",
    )


def create_bot_filter_switch():
    """
    Create the GitHub bot filter switch component.

    Returns:
        dbc.Switch component for bot filtering
    """
    return dbc.Switch(
        id="bot-switch",
        label="GitHub Bot Filter",
        value=True,
        input_class_name="botlist-filter-switch",
        className="bot-filter-switch",
    )


def create_search_controls():
    """
    Create the search control buttons and switches section.

    Returns:
        dbc.Stack component with help, repo list, and bot filter controls
    """
    return dbc.Stack(
        [
            create_button(
                button_id="search-help",
                content=html.I(className="fas fa-question-circle"),
                title="Help",
                custom_class="icon-button",
            ),
            create_button(
                button_id="repo-list-button",
                content=html.I(className="fas fa-list"),
                title="Repo List",
                custom_class="icon-button",
            ),
            create_bot_filter_switch(),
        ],
        direction="horizontal",
        className="search-controls-stack",
    )


def create_search_bar(initial_option):
    """
    Create the complete search bar component with all sub-components.

    Args:
        initial_option: Initial option dictionary for the MultiSelect

    Returns:
        html.Div containing the complete search bar interface
    """
    return html.Div(
        [
            create_search_input_section(initial_option),
        ],
        className="search-bar-wrapper",
    )


def create_bottom_navbar():
    """
    Create the bottom navigation bar with request links.
    Uses CSS variables from color.css and main_layout.css.

    Returns:
        dbc.NavbarSimple component with visualization, bug, and repo request links
    """
    nav_items = [
        {
            "text": "Visualization request",
            "href": "https://github.com/chaoss/8Knot/issues/new?assignees=&labels=enhancement%2Cvisualization&template=visualizations.md",
        },
        {
            "text": "Bug",
            "href": "https://github.com/chaoss/8Knot/issues/new?assignees=&labels=bug&template=bug_report.md",
        },
        {
            "text": "Repo/Org Request",
            "href": "https://github.com/chaoss/8Knot/issues/new?assignees=&labels=augur&template=augur_load.md",
        },
    ]

    # Create nav items using list comprehension
    children = [
        dbc.NavItem(
            dbc.NavLink(
                item["text"],
                href=item["href"],
                external_link=True,
                target="_blank",
            )
        )
        for item in nav_items
    ]

    return dbc.NavbarSimple(
        children=children,
        brand=html.Span(f"v{__version__}", className="version-display"),
        brand_href=None,
        fluid=True,
        fixed="bottom",
        color="var(--bg-primary)",
        dark=True,
    )
