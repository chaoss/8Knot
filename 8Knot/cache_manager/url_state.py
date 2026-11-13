"""Encode/decode the share-link state payload (versioned JSON -> gzip -> base64url)."""

from __future__ import annotations

import io
import gzip
import json
import base64
from collections.abc import Callable

CURRENT_VERSION = 1

# The ?state= blob is attacker-controlled. Cap the decompressed size (zip-bomb
# guard) and the encoded input itself; a legitimate 200-repo payload is < 1 KiB.
MAX_DECODED_BYTES = 64 * 1024
MAX_ENCODED_LEN = 16 * 1024

# Caps on payload collections — bounds the work a crafted link can cause.
_MAX_REPO_IDS = 10_000
_MAX_ORG_NAMES = 1_000

# Maps an OLD version -> a function upgrading a payload by one version (must
# bump "v"). decode_state walks this chain, so bumping CURRENT_VERSION does not
# break previously issued links: they are upgraded in memory on read. Example
# when introducing v2:  MIGRATIONS = {1: _v1_to_v2}
MIGRATIONS: dict[int, Callable[[dict], dict]] = {}


def _migrate(payload: dict) -> dict | None:
    """Upgrade a payload to CURRENT_VERSION, or None if no path exists."""
    v = payload.get("v")
    while v != CURRENT_VERSION:
        migrate = MIGRATIONS.get(v)
        if migrate is None:
            return None
        payload = migrate(payload)
        new_v = payload.get("v")
        if new_v == v:  # a migration that doesn't advance would loop forever
            return None
        v = new_v
    return payload


def encode_state(
    repo_ids: list[int], org_names: list[str], pathname: str, graph_id: str | None, filters: dict | None = None
) -> str:
    payload = {
        "v": CURRENT_VERSION,
        "repo_ids": repo_ids,
        "org_names": org_names,
        "pathname": pathname,
        "graph_id": graph_id,
        "filters": filters or {},
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    compressed = gzip.compress(raw, compresslevel=9)
    return base64.urlsafe_b64encode(compressed).decode().rstrip("=")


def _is_valid_shape(p: dict) -> bool:
    """Type-check every payload field so downstream consumers can trust it.

    Valid JSON can still carry hostile shapes (lists where strings belong,
    unhashable values) that would raise in downstream lookups. bool is
    excluded from ints because isinstance(True, int) is True.
    """
    if not isinstance(p.get("pathname"), str):
        return False
    gid = p.get("graph_id")
    if gid is not None and not isinstance(gid, str):
        return False
    repo_ids = p.get("repo_ids", [])
    if not isinstance(repo_ids, list) or len(repo_ids) > _MAX_REPO_IDS:
        return False
    if not all(isinstance(r, int) and not isinstance(r, bool) for r in repo_ids):
        return False
    org_names = p.get("org_names", [])
    if not isinstance(org_names, list) or len(org_names) > _MAX_ORG_NAMES:
        return False
    if not all(isinstance(o, str) for o in org_names):
        return False
    if not isinstance(p.get("filters", {}), dict):
        return False
    return True


def decode_state(encoded: str) -> dict | None:
    """Decode a ?state= blob into a trusted payload dict, or None if invalid."""
    try:
        if not encoded or len(encoded) > MAX_ENCODED_LEN:
            return None

        padded = encoded + "=" * (-len(encoded) % 4)
        compressed = base64.urlsafe_b64decode(padded)

        # Bounded read: detect oversize without materializing a bomb.
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as f:
            raw = f.read(MAX_DECODED_BYTES + 1)
        if len(raw) > MAX_DECODED_BYTES:
            return None

        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return None
        if payload.get("v") != CURRENT_VERSION:
            payload = _migrate(payload)  # old link: upgrade rather than reject
            if payload is None:
                return None
        if not _is_valid_shape(payload):
            return None
        return payload
    except Exception:
        return None
