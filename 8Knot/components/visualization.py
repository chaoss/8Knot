from dash import html, dcc, Input, State, Output, callback, MATCH
import dash_bootstrap_components as dbc
from typing import Optional


# All-in-One Components should be suffixed with 'AIO'
class VisualizationAIO(dbc.Card):
    def __init__(
        self,
        page: str,
        viz_id: str,
        graph_info="",
        class_name="",
        controls=None,
        title: str = "",
        id: Optional[str] = None,
    ):
        """
        Common visualization shell to be shared by all visualizations

        Args:
            page (str): The name of the page this visualization is part of
            viz_id (str): a unique id for this visualization
            graph_info (str): The description of this graph giving more information on what it describes and where its data came from. Displayed in a popover.
            class_name (str): Any custom class names to associate with this card
            controls (list): A list of form elements to display within the lower form Row at the bottom of the graph
            title (Optional[str]): a static title. If none, the title will be fetched from a callback with the id "graph-title-{page}-{viz_id}". Defaults to none.
            id (Optional[str]): an identifier to use to jump to the card. Primarily intended for navigation, not for styling. Defaults to none, which causes {page}-{viz_id} to be used
        """
        self.page = page
        self.viz_id = viz_id
        self.nav_id = id

        if controls is None:
            controls = []

        # Define the component's layout
        super().__init__(
            [
                dbc.CardBody(
                    [
                        dbc.Row(
                            [
                                dbc.Col(html.H3(title, id=f"graph-title-{page}-{viz_id}", className="card-title")),
                                dbc.Col(
                                    [
                                        dbc.Button(
                                            [html.I(className="fas fa-share-alt me-1"), "Share"],
                                            id={"type": "share-btn", "graph": viz_id, "page": page},
                                            color="outline-info",
                                            size="sm",
                                            className="share-graph-button me-2",
                                        ),
                                        dbc.Button(
                                            "About Graph",
                                            id={"type": "popover-target", "index": f"{page}-{viz_id}"},
                                            color="outline-secondary",
                                            size="sm",
                                            className="about-graph-button",
                                        ),
                                    ],
                                    width="auto",
                                    className="d-flex align-items-center",
                                ),
                            ],
                            align="center",
                            justify="between",
                            className="mb-3",
                        ),
                        dbc.Popover(
                            [
                                dbc.PopoverHeader("Graph Info:"),
                                dbc.PopoverBody(graph_info),
                            ],
                            id={"type": "popover", "index": f"{page}-{viz_id}"},
                            target={"type": "popover-target", "index": f"{page}-{viz_id}"},
                            placement="top",
                            is_open=False,
                        ),
                        dcc.Loading(
                            dcc.Graph(id=f"{page}-{viz_id}"),
                            style={"marginBottom": "1rem"},
                        ),
                        html.Hr(className="card-split") if controls else None,  # Divider between graph and controls
                        (
                            dbc.Form(
                                [
                                    dbc.Row(
                                        controls,
                                        align="center",
                                        justify="start",
                                    ),
                                ]
                            )
                            if controls
                            else None
                        ),
                    ],
                    style={"padding": "1.5rem"},
                ),
            ],
            className=class_name,
            id=(self.nav_id if self.nav_id is not None else f"{self.page}-{self.viz_id}"),
        )

    # callback for graph info popover
    @callback(
        Output({"type": "popover", "index": MATCH}, "is_open"),
        [Input({"type": "popover-target", "index": MATCH}, "n_clicks")],
        [State({"type": "popover", "index": MATCH}, "is_open")],
    )
    def toggle_popover(n, is_open):
        if n:
            return not is_open
        return is_open
