"""Opaque offset-based cursor pagination.

Lists respond with {"items": [...], "next_cursor": str|null, "has_more": bool}.
The cursor is base64-encoded JSON {"o": offset}; treat it as opaque.
"""

from __future__ import annotations

import base64
import json
from typing import Any, TypeVar

from app.api.errors import ApiError

ItemT = TypeVar("ItemT")

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        offset = int(payload["o"])
        if offset < 0:
            raise ValueError("negative offset")
        return offset
    except Exception as exc:
        raise ApiError(
            400, "invalid_cursor", f"malformed pagination cursor: {cursor!r}"
        ) from exc


def encode_cursor(offset: int) -> str:
    raw = json.dumps({"o": offset}).encode()
    return base64.urlsafe_b64encode(raw).decode()


def paginate(
    all_items: list[ItemT], offset: int, limit: int
) -> dict[str, Any]:
    """Offsets a fully materialized (already filtered, ordered) list.

    Collections in V1 are small (per-document/pilote scale); the API shape is
    keyset-ready should real corpus sizes demand it.
    """
    window = all_items[offset : offset + limit]
    has_more = offset + limit < len(all_items)
    return {
        "items": window,
        "next_cursor": encode_cursor(offset + limit) if has_more else None,
        "has_more": has_more,
    }


def clamp_limit(limit: int) -> int:
    if limit < 1 or limit > MAX_LIMIT:
        raise ApiError(
            400,
            "invalid_limit",
            f"limit must be between 1 and {MAX_LIMIT}",
        )
    return limit
