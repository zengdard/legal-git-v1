"""Source registry helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.sources.models import Source


def get_or_create_source(
    session: Session,
    *,
    source_id: str,
    name: str,
    publisher: str | None,
    jurisdiction: str,
    source_type: str,
    base_uri: str | None = None,
    licence_name: str | None = None,
    licence_uri: str | None = None,
) -> tuple[Source, bool]:
    source = session.get(Source, source_id)
    if source is not None:
        return source, False
    source = Source(
        id=source_id,
        name=name,
        publisher=publisher,
        jurisdiction=jurisdiction,
        source_type=source_type,
        base_uri=base_uri,
        licence_name=licence_name,
        licence_uri=licence_uri,
    )
    session.add(source)
    session.flush()
    return source, True


def list_sources(session: Session, offset: int = 0, limit: int = 20) -> list[Source]:
    statement = select(Source).order_by(Source.id).offset(offset).limit(limit)
    return list(session.scalars(statement))
