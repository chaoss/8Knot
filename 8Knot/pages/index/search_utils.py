"""
Search utilities for the 8Knot application.
Provides improved search algorithms and layout components for the searchbar.
Uses Dash All-in-One Components pattern for reusable, generic components.

Generic Builders (All-in-One Pattern):
    create_alert: Build any type of alert component
    create_store: Build client-side storage components
    create_button: Build buttons or nav links

Search-Specific Functions:
    fuzzy_search: Advanced fuzzy matching algorithm
    create_search_bar: Complete search bar with all features
    create_bottom_navbar: Bottom navigation with request links
"""

from typing import List, Dict, Any, Optional, Union
import re

# Going with rapidfuzz instead of fuzzywuzzy
# as it's more performant and supports score_cutoff
from rapidfuzz import fuzz, process

# Dash imports for layout components
from dash import html, dcc
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

from metadata import __version__


def search_short_query(query: str, options: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Optimized search for very short queries (1-2 characters).
    Uses simple prefix and contains matching for better performance.

    Args:
        query: Short search query string
        options: List of dictionaries with 'label' and 'value' keys

    Returns:
        List of matching options prioritizing prefix matches
    """
    starts_with_matches = []
    contains_matches = []
    query_lower = query.lower()

    # Separate into prefix matches and contains matches
    for option in options:
        # Get the label and convert to lowercase once
        label = option["label"].lower()
        if label.startswith(query_lower):
            starts_with_matches.append(option)
        elif query_lower in label:
            contains_matches.append(option)

    # Limit results
    max_starts_with = min(50, len(starts_with_matches))
    max_contains = min(50, len(contains_matches))

    return starts_with_matches[:max_starts_with] + contains_matches[:max_contains]


def search_with_fuzzy_matching(
    query: str, options: List[Dict[str, Any]], threshold: float, limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Perform fuzzy search using the rapidfuzz library for longer queries.
    Enhanced to prioritize exact substring matches.

    Args:
        query: Search query string
        options: List of dictionaries with 'label' and 'value' keys
        threshold: Minimum similarity score to include in results (0-1)
        limit: Maximum number of results to return (None = all results)

    Returns:
        List of matching options sorted by relevance
    """
    if not options:
        return []

    # Convert threshold to the 0-100 scale used by rapidfuzz
    threshold_100 = int(threshold * 100)
    query_lower = query.lower()

    exact_matches = []
    fuzzy_matches = []

    # First pass: find exact substring matches (highest priority)
    for opt in options:
        label_lower = opt["label"].lower()
        if query_lower in label_lower:
            exact_matches.append(opt)
            # Early termination if we have enough exact matches and limit is set
            if limit and len(exact_matches) >= limit:
                return exact_matches[:limit]

    # Second pass: find fuzzy matches for items not already matched exactly
    exact_labels = set(opt["label"] for opt in exact_matches)
    remaining_options = [opt for opt in options if opt["label"] not in exact_labels]

    if remaining_options:
        # Calculate how many fuzzy matches we need (if limit is set)
        fuzzy_limit = None
        if limit:
            fuzzy_limit = max(0, limit - len(exact_matches))
            if fuzzy_limit == 0:
                return exact_matches  # Already have enough exact matches

        # Use fuzzy matching for remaining options
        matches = process.extract(
            query_lower,  # Use lowercased query
            [opt["label"] for opt in remaining_options],
            scorer=fuzz.token_sort_ratio,
            processor=str.lower,
            limit=fuzzy_limit,  # Use calculated limit or None for comprehensive
            score_cutoff=threshold_100,
        )

        # Map back to original option objects
        remaining_options_dict = {opt["label"]: opt for opt in remaining_options}

        # Handle the return format from rapidfuzz which returns (match, score, index)
        for match_data in matches:
            # Extract just the label (first element)
            label = match_data[0]
            if label in remaining_options_dict:
                fuzzy_matches.append(remaining_options_dict[label])

    # Combine results: exact matches first, then fuzzy matches
    return exact_matches + fuzzy_matches


def calculate_token_score(token: str, label: str, label_tokens: List[str]) -> float:
    """
    Calculate the match score for a single token against a label.

    Args:
        token: Single search token
        label: Full label
        label_tokens: Tokenized version of the label

    Returns:
        float: Score between 0 and 1 representing match quality
    """
    # Try exact contains first (high confidence match)
    if token in label:
        return 0.95

    # If no exact match, find best fuzzy match among label tokens
    best_score = 0.0
    for label_token in label_tokens:
        # Use rapidfuzz's token_sort_ratio for better matching
        score = fuzz.token_sort_ratio(token, label_token) / 100.0
        best_score = max(best_score, score)

    return best_score


def fuzzy_search(
    query: str, options: List[Dict[str, Any]], threshold: float = 0.2, limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Perform fuzzy search on a list of options using rapidfuzz, case-insensitive.

    Args:
        query: Search query string
        options: List of dictionaries with 'label' and 'value' keys
        threshold: Minimum similarity score to include in results (0-1)
        limit: Maximum number of results to return (None = all results)

    Returns:
        List of matching options sorted by relevance
    """
    if not query:
        return options

    # For very short queries (1-2 chars), use a simpler and faster matching approach
    if len(query) <= 2:
        return search_short_query(query, options)
    else:
        return search_with_fuzzy_matching(query, options, threshold, limit)


def tokenize_search(query: str) -> List[str]:  # Function breaks down a search query into smaller parts (tokens)
    """
    Split search query into tokens for more flexible matching.

    token -> meaningful unit of text extracted from a larger string
    example: if the search query is "Project Aspen: 8Knot and Augur", then the tokens are ["project", "aspen", "8knot", "augur"]

    Args:
        query: Search query string

    Returns:
        List of tokens from the query
    """
    return [token.strip().lower() for token in re.split(r"[\s/_.,-]+", query) if token.strip()]


def token_match_score(tokens: List[str], label: str) -> float:
    """
    Calculate match score based on tokens using fuzzywuzzy.

    Args:
        tokens: List of search tokens
        label: String to match against

    Returns:
        float: Score between 0 and 1
    """
    if not tokens:
        return 0.0

    # Convert to lowercase once
    label_lower = label.lower()
    # tokenize_search already handles lowercase conversion internally
    label_tokens = tokenize_search(label)

    # Calculate individual token match scores
    match_scores = [calculate_token_score(token, label_lower, label_tokens) for token in tokens]

    # Average the scores
    if match_scores:
        return sum(match_scores) / len(match_scores)
    return 0.0


def clean_repo_name(repo_name: str) -> tuple[str, str]:
    """
    Clean repository names by removing GitHub and GitLab URL prefixes.

    Supports both GitHub and GitLab repositories for future compatibility.

    Args:
        repo_name: The original repository name/URL

    Returns:
        Tuple of (cleaned_name, platform) where platform is 'github', 'gitlab', or 'unknown'
    """
    if not repo_name:
        return repo_name, "unknown"

    # Define prefixes with their corresponding platforms
    github_prefixes = ["https://github.com/"]

    gitlab_prefixes = ["https://gitlab.com/"]

    cleaned_name = repo_name
    repo_name_lower = repo_name.lower()

    # Check GitHub prefixes
    for prefix in github_prefixes:
        if repo_name_lower.startswith(prefix):
            cleaned_name = cleaned_name[len(prefix) :]
            return cleaned_name, "github"

    # Check GitLab prefixes
    for prefix in gitlab_prefixes:
        if repo_name_lower.startswith(prefix):
            cleaned_name = cleaned_name[len(prefix) :]
            return cleaned_name, "gitlab"

    # No known prefix found
    return cleaned_name, "unknown"


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


def create_store(
    store_id: str,
    storage_type: str = "session",
    data: Optional[Any] = None,
) -> dcc.Store:
    """
    Generic store component builder for client-side storage.

    Args:
        store_id: Unique identifier for the store
        storage_type: Type of storage ('session', 'local', or 'memory')
        data: Optional initial data

    Returns:
        dcc.Store component configured with provided parameters
    """
    return dcc.Store(id=store_id, storage_type=storage_type, data=data)


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


def create_search_storage_components():
    """
    Create storage components for client-side caching and cache initialization.
    Uses the generic store builder.

    Returns:
        List of dcc.Store and html.Div components for search caching
    """
    return [
        create_store("cached-options", storage_type="session"),
        html.Div(id="cache-init-trigger", className="hidden"),
        create_store("search-cache-init-hidden", storage_type="session"),
    ]


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
        data=[initial_option],
        value=[initial_option["value"]],
        # Start with "searching" class so default selection (chaoss) shows as blue
        className="searchbar-dropdown searching",
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
            *create_search_storage_components(),
            html.Div(
                create_alert(
                    alert_id="storage-quota-warning",
                    children="Browser storage limit reached. Search will use a reduced cache which may slightly impact performance. All features will still work normally.",
                    color="warning",
                    icon_class="quota-warning-icon",
                    custom_class="mt-2 mb-0 hidden",
                ),
                className="search-bar-component",
            ),
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
