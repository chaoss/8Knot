"""
Share-link UI: the modal and its supporting stores/alert.

Layout only — callbacks live in `share_callbacks.py`. Kept SEPARATE from
`index_components.py` on purpose: mixing share components into the app-stores
list broke Dash's page rendering in earlier attempts (Toasts/Clipboards are
not inert stores). Everything is wrapped in one `html.Div` so the layout file
adds a single child, as a sibling of the existing layout — never inside
`create_app_stores()`.
"""

from dash import html, dcc
import dash_bootstrap_components as dbc


def create_share_modal() -> html.Div:
    """Return the share modal + state stores, to be appended to the main container."""
    return html.Div(
        id="share-system-container",
        children=[
            # Channel for URL-loaded share payloads; feeds the existing
            # search flow instead of writing `repo-choices` directly.
            dcc.Store(id="share-loaded-state", data=None),
            # No-op output target for the clientside scroll-to-anchor callback.
            dcc.Store(id="share-scroll-dummy", data=None),
            # Feedback when a shared link fails to load (invalid/removed).
            dbc.Alert(
                "",
                id="share-load-alert",
                is_open=False,
                dismissable=True,
                color="warning",
                className="share-load-alert",
            ),
            dbc.Modal(
                id="share-modal",
                is_open=False,
                size="lg",
                children=[
                    dbc.ModalHeader(dbc.ModalTitle("Share this graph")),
                    dbc.ModalBody(
                        [
                            html.P(
                                "Copy the link below to share this exact view "
                                "(repositories + graph) with someone else.",
                                className="mb-2",
                            ),
                            dbc.InputGroup(
                                [
                                    dbc.Input(
                                        id="share-url-display",
                                        type="text",
                                        readonly=True,
                                        value="",
                                    ),
                                    dbc.Button(
                                        [html.I(className="fas fa-copy me-1"), "Copy"],
                                        id="share-copy-button",
                                        color="primary",
                                        n_clicks=0,
                                    ),
                                ]
                            ),
                            html.Div(
                                id="share-status-message",
                                className="mt-2 text-success",
                            ),
                            html.Div(
                                id="share-warning-text",
                                className="mt-2 text-warning",
                            ),
                        ]
                    ),
                    dbc.ModalFooter(
                        dbc.Button(
                            "Close",
                            id="share-modal-close",
                            color="secondary",
                            n_clicks=0,
                        )
                    ),
                ],
            ),
        ],
    )
