from dash import html, dcc
import dash
import dash_bootstrap_components as dbc

# Import welcome sections for tabs
try:
    from .sections.pages_overview_section import layout as general_tab_contents
    from .sections.plotly_section import layout as plotly_tab_contents
    from .sections.how_8knot_works_section import layout as how_8knot_works_tab_contents
    from .sections.definitions_section import layout as definitions_tab_contents

    # from .sections.augur_login_section import layout as augur_tab_contents
    # from .sections.user_group_section import layout as group_tab_contents
except ImportError:
    # Fallback if sections don't exist
    general_tab_contents = html.Div("General section not available")
    plotly_tab_contents = html.Div("Plotly section not available")
    how_8knot_works_tab_contents = html.Div("How 8knot works section not available")
    definitions_tab_contents = html.Div("Definitions section not available")
    # augur_tab_contents = html.Div("Augur section not available")
    # group_tab_contents = html.Div("User group section not available")

# Register this as the main landing page
dash.register_page(__name__, path="/", order=1, title="Welcome")


def create_landing_hero():
    """Create the main hero section with 8Knot logo and title."""
    return html.Div(
        className="landing-hero",
        children=[
            # Logo section
            html.Div(
                className="landing-logo-section",
                children=[
                    html.Img(
                        src="/assets/8Knot.svg",
                        alt="8Knot Logo",
                        className="landing-logo",
                    ),
                    html.H1(
                        "Advanced open source project analysis",
                        className="landing-title",
                    ),
                    html.P(
                        "8Knot visualizes the rich dataset collected by CollectOSS. The duo enriches the study of communities for community architects, developers, and business intelligence experts alike.",
                        className="landing-subtitle",
                    ),
                ],
            ),
            # Learn button section
            html.Div(
                className="landing-cta-section",
                children=[
                    html.P(
                        "Is this your first time here?",
                        className="landing-cta-text",
                    ),
                    dbc.Button(
                        [
                            "Learn how 8Knot works ",
                            html.I(
                                id="learn-button-icon",
                                className="fas fa-chevron-down landing-button-icon",
                            ),
                        ],
                        id="learn-button",
                        className="landing-learn-button",
                        color="light",
                    ),
                ],
            ),
        ],
    )


def create_welcome_content():
    """Create the expandable welcome content section with DBC tabs in cards."""
    return html.Div(
        id="welcome-content",
        className="landing-welcome-content how-8knot-works-section",
        children=[
            html.Div(
                className="section-title-container",
                children=[
                    html.H1("8Knot Documentation", className="section-title"),
                ],
                style={"display": "none"},  # Hidden as per Figma design
            ),
            # DBC Card with Tabs Container
            dbc.Card(
                [
                    # Card Header with Tabs
                    dbc.CardHeader(
                        dbc.Tabs(
                            id="welcome-tabs",
                            active_tab="plotlyfiguretools",
                            className="landing-tabs-redesigned",
                            children=[
                                dbc.Tab(
                                    label="Using 8Knot Visualizations",
                                    tab_id="plotlyfiguretools",
                                    label_class_name="landing-tab-redesigned tab01",
                                    active_label_class_name="landing-tab-redesigned landing-tab-redesigned--selected tab01",
                                ),
                                dbc.Tab(
                                    label="8Knot Pages",
                                    tab_id="general",
                                    label_class_name="landing-tab-redesigned tab02",
                                    active_label_class_name="landing-tab-redesigned landing-tab-redesigned--selected tab02",
                                ),
                                dbc.Tab(
                                    label="How 8Knot Works",
                                    tab_id="how8knotworks",
                                    label_class_name="landing-tab-redesigned tab03",
                                    active_label_class_name="landing-tab-redesigned landing-tab-redesigned--selected tab03",
                                ),
                                dbc.Tab(
                                    label="Definitions",
                                    tab_id="definitions",
                                    label_class_name="landing-tab-redesigned tab04",
                                    active_label_class_name="landing-tab-redesigned landing-tab-redesigned--selected tab04",
                                ),
                            ],
                        ),
                        className="tabs-header",
                    ),
                    # Card Body with Content Container
                    dbc.CardBody(
                        className="tab-content-container",
                        children=[
                            # Side Navigation
                            html.Div(
                                className="side-nav",
                                children=[
                                    html.Div(
                                        className="tab-title",
                                        children=[
                                            html.Div(
                                                className="content",
                                                children=[
                                                    html.Span(
                                                        "Using 8Knot Visualizations",
                                                        id="current-tab-title",
                                                        className="tab-title-text",
                                                    ),
                                                    html.Div(className="arrow"),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            # Main Content Area
                            html.Div(
                                id="tab-content-main",
                                className="tab-content-main",
                                children=[plotly_tab_contents],  # Default content
                            ),
                        ],
                    ),
                ],
                className="card-container",
            ),
        ],
    )


# Main layout for the landing page
layout = html.Div(
    className="landing-page",
    children=[
        create_landing_hero(),
        create_welcome_content(),
        # Store to track welcome content state
        dcc.Store(id="welcome-content-state", data={"expanded": False}),
    ],
)
