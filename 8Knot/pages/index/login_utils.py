"""
Login utilities
Provides modular components for login banner and navigation elements.

Generic Builders (All-in-One Pattern):
    create_nav_item: Build any type of navigation item

Login-Specific Functions:
    create_login_navbar: Main login navigation bar
    create_login_disabled_banner: Banner shown when login is disabled
    is_login_enabled: Check login status from environment
"""

import os
from typing import Optional, Dict, Any, Union, List, TYPE_CHECKING
from dash import html, dcc
import dash_bootstrap_components as dbc

# Use TYPE_CHECKING to avoid circular imports
if TYPE_CHECKING:
    from db_manager.augur_manager import AugurManager


# ===== GENERIC COMPONENT BUILDERS (All-in-One Pattern) =====


def create_nav_item(
    item_id: str,
    content: str,
    disabled: bool = False,
    href: Optional[str] = None,
    external_link: bool = False,
    target: Optional[str] = None,
) -> dbc.NavItem:
    """
    Generic navigation item builder following Dash All-in-One Components pattern.

    Args:
        item_id: Unique identifier for the nav item
        content: Text content for the nav link
        disabled: Whether the nav item is disabled
        href: Link URL (optional)
        external_link: Whether link is external
        target: Link target attribute

    Returns:
        dbc.NavItem containing a configured NavLink
    """
    return dbc.NavItem(
        dbc.NavLink(
            content,
            id=item_id,
            disabled=disabled,
            href=href,
            external_link=external_link,
            target=target,
        ),
    )


# ===== LOGIN COMPONENT FUNCTIONS =====


def create_login_disabled_alert():
    """
    Create the alert content for the login disabled banner.
    Uses CSS classes from main_layout.css for consistent styling.

    Returns:
        dbc.Alert component with login disabled message
    """
    return dbc.Alert(
        [
            html.H4(
                "Login is Currently Disabled",
                className="alert-heading login-banner-heading",
            ),
            html.P(
                [
                    "If you need to collect data on new repositories, please ",
                    html.A(
                        "create a repository collection request",
                        href="https://github.com/chaoss/8Knot/issues/new?template=augur_load.md",
                        target="_blank",
                        className="login-banner-link",
                    ),
                    ".",
                ],
                className="login-banner-text",
            ),
        ],
        color="light",
        dismissable=True,
        duration=60000,
        id="login-disabled-banner",
        className="mb-0 login-banner-alert",
    )


def create_login_disabled_banner():
    """
    Create the banner displayed when login is disabled.
    Uses CSS class .login-banner-container for positioning.

    Returns:
        html.Div containing the login disabled banner, or None if login is enabled
    """
    if not is_login_enabled():
        return html.Div(
            create_login_disabled_alert(),
            className="login-banner-container",
        )
    return None


def create_login_container():
    """
    Create the login container with loading indicator.

    Returns:
        dcc.Loading component wrapping the nav-login-container
    """
    return dcc.Loading(
        children=[
            html.Div(
                id="nav-login-container",
                children=[],
            ),
        ]
    )


def create_login_popover():
    """
    Create the login failed popover.

    Returns:
        dbc.Popover component for login failure notifications
    """
    return dbc.Popover(
        children="Login Failed",
        body=True,
        id="login-popover",
        is_open=False,
        placement="bottom-end",
        target="nav-dropdown",
    )


def create_login_nav(augur_manager: "AugurManager"):
    """
    Create the login navigation component with all items.
    Uses the generic create_nav_item builder directly.

    Args:
        augur_manager: The AugurManager instance with user_account_endpoint attribute

    Returns:
        dbc.Nav component with all login navigation items
    """
    return dbc.Nav(
        [
            create_login_container(),
            create_nav_item(
                item_id="refresh-button",
                content="Refresh Groups",
                disabled=True,
            ),
            create_nav_item(
                item_id="manage-group-button",
                content="Manage Groups",
                disabled=True,
                href=f"{augur_manager.user_account_endpoint}?section=tracker",
                external_link=True,
                target="_blank",
            ),
            create_nav_item(
                item_id="logout-button",
                content="Log out",
                disabled=True,
                href="/logout/",
                external_link=True,
            ),
            create_login_popover(),
        ]
    )


def create_login_navbar(augur_manager: "AugurManager"):
    """
    Create the login navbar based on AUGUR_LOGIN_ENABLED environment variable.

    Args:
        augur_manager: The AugurManager instance (only used if login is enabled)

    Returns:
        List containing the login navbar Row, or empty Div if login is disabled
    """
    if is_login_enabled():
        return [
            dbc.Row(
                [dbc.Col(create_login_nav(augur_manager))],
                align="center",
            ),
        ]
    else:
        return [html.Div()]


def is_login_enabled():
    """
    Check if login is enabled via environment variable.

    Returns:
        bool: True if login is enabled, False otherwise
    """
    return os.getenv("AUGUR_LOGIN_ENABLED", "False") == "True"
