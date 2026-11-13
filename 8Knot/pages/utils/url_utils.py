"""
Pure URL helpers for the shareable-link system.

String composition and parsing only — no Dash coupling and no knowledge of
which graphs exist (that domain logic lives in ``graph_registry.py``).
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit


def compose_share_url(base: str, encoded_state: str, pathname: str, anchor: str | None) -> str:
    """Assemble ``<base><pathname>?state=<blob>[#anchor]``.

    ``anchor`` is the target graph card's DOM id (``f"{page}-{viz_id}"``) so the
    browser-side scroll handler can land on the exact graph.
    """
    frag = f"#{anchor}" if anchor else ""
    return f"{base.rstrip('/')}{pathname}?state={encoded_state}{frag}"


def extract_base_url(href: str) -> str:
    """Return ``scheme://netloc`` from a full href, robust to path collisions.

    Using urlsplit (rather than string slicing on the pathname) means a
    hostname that happens to contain the pathname can't corrupt the result.
    """
    parts = urlsplit(href or "")
    return f"{parts.scheme}://{parts.netloc}"


def extract_url_params(search: str) -> dict:
    if not search:
        return {}
    params = parse_qs(search.lstrip("?"))
    return {
        "state": (params.get("state") or [None])[0],
    }
