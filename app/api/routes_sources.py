"""Source registry endpoints (read-only)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.api.errors import ApiError
from app.api.pagination import DEFAULT_LIMIT, clamp_limit, decode_cursor
from app.api.schemas import Page, SourceOut
from app.sources import service as sources_service

router = APIRouter(prefix="/sources", tags=["sources"])


def _source_out(source) -> SourceOut:
    return SourceOut(
        id=source.id,
        name=source.name,
        publisher=source.publisher,
        jurisdiction=source.jurisdiction,
        source_type=source.source_type,
        base_uri=source.base_uri,
        licence_name=source.licence_name,
        licence_uri=source.licence_uri,
        created_at=source.created_at,
    )


@router.get("", response_model=Page)
def list_sources(
    session: SessionDep,
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> Page:
    limit = clamp_limit(limit)
    items = sources_service.list_sources(session, offset=decode_cursor(cursor), limit=limit)
    # list_sources already windowed; rebuild the page shape.
    has_more = len(items) == limit
    from app.api.pagination import encode_cursor

    page = {
        "items": [_source_out(s) for s in items],
        "next_cursor": encode_cursor(decode_cursor(cursor) + limit) if has_more else None,
        "has_more": has_more,
    }
    return Page(**page)


@router.get("/{source_id}", response_model=SourceOut)
def get_source(source_id: str, session: SessionDep) -> SourceOut:
    from app.sources.models import Source

    source = session.get(Source, source_id)
    if source is None:
        raise ApiError(404, "not_found", f"source {source_id!r} not found")
    return _source_out(source)
