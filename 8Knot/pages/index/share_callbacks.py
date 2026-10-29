"""
Callbacks for the shareable URL system.

The whole share is carried in the URL: the searchbar selection + target graph
are serialized into a versioned gzip+base64url payload under ``?state=``. No
database — the link is self-contained and survives any cache reset. (A
DB-backed short-URL layer, ``?s=<id>``, is a planned follow-up PR.)

Integration rules (each one prevents a class of Dash breakage):
  * Share UI lives in `share_components.create_share_modal()`, NOT in the
    app stores list.
  * The load path never writes `repo-choices` directly — it populates
    `projects` and bumps `search-button.n_clicks`, reusing the existing
    search pipeline (no `allow_duplicate` races).
  * Only ONE callback reads `url.search`.
  * Pattern-matching share-button IDs are callback INPUTS only; every
    OUTPUT targets a simple string-id modal component.
"""

from __future__ import annotations

import dash
from dash import callback, ctx, clientside_callback
from dash.dependencies import Input, Output, State, ALL

from app import augur
import cache_manager.url_state as url_state
from pages.utils import url_utils
from pages.utils import graph_registry
from models import SearchItem


# -----------------------------------------------------------------------------
# Helpers (pure orchestration — no Dash coupling)
# -----------------------------------------------------------------------------


def _split_selection(selection: list[str] | None) -> tuple[list[int], list[str]]:
    """Split a searchbar selection into ``(repo_ids, org_names)``.

    Repos are numeric values, orgs are not (see ``SearchItem.from_id``).
    Keeping orgs separate lets a shared link restore the single org pill —
    not its expanded repos — and re-resolve the org's membership on load.
    """
    repo_ids, org_names = [], []
    for v in selection or []:
        if SearchItem.from_id(v) == SearchItem.REPO:
            repo_ids.append(int(v))
        else:
            org_names.append(v)
    return repo_ids, org_names


def _build_share_url(selection: list[str], pathname: str, href: str, page: str | None, graph_id: str | None) -> str:
    """Encode the selection into a self-contained share URL.

    The URL fragment must be the card's real DOM id, ``f"{page}-{viz_id}"``
    (see ``VisualizationAIO``) — the bare viz_id matches no element.
    """
    repo_ids, org_names = _split_selection(selection)
    base_url = url_utils.extract_base_url(href)
    encoded = url_state.encode_state(
        repo_ids=repo_ids,
        org_names=org_names,
        pathname=pathname,
        graph_id=graph_id,
    )
    anchor = f"{page}-{graph_id}" if (page and graph_id) else None
    return url_utils.compose_share_url(base_url, encoded, pathname, anchor)


def _resolve_selection(repo_ids: list[int], org_names: list[str]) -> tuple[list[dict], list[str], list[int | str]]:
    """Rebuild searchbar ``(options, values, missing)`` from a decoded payload.

    Each present item needs a matching ``{value, label}`` option because
    dmc.MultiSelect drops values absent from its ``data``. Items unknown to
    this instance go to ``missing`` ("load remaining + warn" behavior).
    """
    options, values, missing = [], [], []

    for rid in repo_ids:
        git_url = augur.repo_id_to_git(rid)
        if git_url:
            label = git_url[8:] if git_url.startswith("https://") else git_url
            options.append({"value": str(rid), "label": label})
            values.append(str(rid))
        else:
            missing.append(rid)

    for org in org_names:
        if augur.is_org(org):
            options.append({"value": org, "label": org})
            values.append(org)
        else:
            missing.append(org)

    return options, values, missing


# -----------------------------------------------------------------------------
# Callbacks
# -----------------------------------------------------------------------------


@callback(
    Output("share-modal", "is_open"),
    Output("share-url-display", "value"),
    Output("share-warning-text", "children"),
    Output("share-status-message", "children"),
    Input({"type": "share-btn", "graph": ALL, "page": ALL}, "n_clicks"),
    Input("share-modal-close", "n_clicks"),
    State("projects", "value"),
    State("url", "pathname"),
    State("url", "href"),
    prevent_initial_call=True,
)
def manage_share_modal(share_clicks, close_clicks, selection, pathname, href):
    """Open the share modal with a generated link, or close it.

    Shares the searchbar *selection* (not the resolved ``repo-choices``) so an
    org stays an org. The clicked graph comes from ``ctx.triggered_id``.
    """
    triggered = ctx.triggered_id

    if triggered == "share-modal-close":
        return False, "", "", ""

    # Pattern inputs can fire with all-None on layout changes; ignore those.
    if not isinstance(triggered, dict) or not any(c for c in (share_clicks or []) if c):
        raise dash.exceptions.PreventUpdate

    if not selection:
        return True, "", "Run a search (select repositories) before sharing.", ""

    url = _build_share_url(selection, pathname, href, triggered.get("page"), triggered.get("graph"))
    return True, url, "", ""


# Clipboard copy runs client-side (dcc.Clipboard has render quirks). Returning
# the writeText promise reports the true outcome instead of assuming success;
# navigator.clipboard is undefined on insecure (HTTP) contexts.
clientside_callback(
    """
    function(n_clicks, url) {
        if (!n_clicks || !url) { return window.dash_clientside.no_update; }
        var fallback = "Copy failed — press Ctrl/Cmd+C to copy the selected link.";
        if (!navigator.clipboard) { return fallback; }
        return navigator.clipboard.writeText(url)
            .then(function () { return "Link copied to clipboard!"; })
            .catch(function () { return fallback; });
    }
    """,
    Output("share-status-message", "children", allow_duplicate=True),
    Input("share-copy-button", "n_clicks"),
    State("share-url-display", "value"),
    prevent_initial_call=True,
)


@callback(
    Output("share-loaded-state", "data"),
    Output("share-load-alert", "is_open"),
    Output("share-load-alert", "children"),
    Input("url", "search"),
    prevent_initial_call=False,
)
def handle_share_url(search):
    """Resolve a ``?state=`` URL into a payload for the load pipeline.

    The only callback reading ``url.search``; it writes only to its own store
    and alert, so it is safe to run alongside Dash's page routing on load.
    """
    raw_state = url_utils.extract_url_params(search).get("state")
    if not raw_state:
        raise dash.exceptions.PreventUpdate  # normal navigation, no share params

    state = url_state.decode_state(raw_state)
    if state is None:
        return None, True, "This shared link is in an outdated or invalid format."

    is_valid, _ = graph_registry.validate_target(state.get("pathname"), state.get("graph_id"))
    if not is_valid:
        return None, True, "The graph referenced by this link no longer exists."

    repo_ids = state.get("repo_ids", [])
    org_names = state.get("org_names", [])
    options, values, missing = _resolve_selection(repo_ids, org_names)

    if not values:
        return None, True, "None of the repositories/organizations in this link are available on this instance."

    payload = {"options": options, "values": values}

    if missing:
        total = len(repo_ids) + len(org_names)
        msg = f"Loaded {len(values)} of {total} selections. {len(missing)} are no longer available on this instance."
        return payload, True, msg

    return payload, False, ""


@callback(
    Output("projects", "data", allow_duplicate=True),
    Output("projects", "value"),
    Output("search-button", "n_clicks"),
    Input("share-loaded-state", "data"),
    State("search-button", "n_clicks"),
    prevent_initial_call=True,
)
def apply_share_state(loaded, current_clicks):
    """Feed a loaded share payload into the existing search pipeline.

    Sets the searchbar selection and bumps ``search-button.n_clicks`` so
    ``multiselect_values_to_repo_ids`` populates ``repo-choices`` exactly as a
    manual search would. ``projects.data`` needs ``allow_duplicate=True``; its
    base writer fires on a disjoint trigger (``searchValue``), so no race.
    """
    if not loaded or not loaded.get("values"):
        raise dash.exceptions.PreventUpdate

    return loaded["options"], loaded["values"], (current_clicks or 0) + 1


# Scroll the shared graph into view. The page is client-side rendered, so the
# native hash scroll fires before the target exists; then graphs above it load
# and reflow the page. So: poll until the card exists, re-scroll at growing
# delays through the reflow, and stop as soon as the user scrolls themselves.
# Keyed on url.hash, so sidebar "#graph" anchors get working scroll too.
clientside_callback(
    """
    function(hash_, _loaded) {
        if (!hash_) { return window.dash_clientside.no_update; }
        var id;
        try { id = decodeURIComponent(hash_.replace(/^#/, '')); }
        catch (e) { return window.dash_clientside.no_update; }
        if (!id) { return window.dash_clientside.no_update; }
        var cancelled = false;
        function onUserScroll() { cancelled = true; }
        function scrollToTarget() {
            if (cancelled) { return true; }
            var el = document.getElementById(id);
            if (!el) { return false; }
            el.scrollIntoView({behavior: 'smooth', block: 'center'});
            return true;
        }
        var tries = 0;
        (function findThenScroll() {
            if (cancelled) { return; }
            if (scrollToTarget()) {
                window.addEventListener('wheel', onUserScroll, {passive: true, once: true});
                window.addEventListener('touchmove', onUserScroll, {passive: true, once: true});
                // re-scroll through ~5.5s of async graph-load reflow
                [400, 1000, 2000, 3500, 5500].forEach(function(d) { setTimeout(scrollToTarget, d); });
                return;
            }
            // poll up to ~5s for the client-side-rendered card to appear
            if (tries++ < 20) { setTimeout(findThenScroll, 250); }
        })();
        return window.dash_clientside.no_update;
    }
    """,
    Output("share-scroll-dummy", "data"),
    Input("url", "hash"),
    Input("share-loaded-state", "data"),
    prevent_initial_call=False,
)
