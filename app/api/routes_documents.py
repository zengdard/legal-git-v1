"""Documents, hierarchy, snapshots and snapshot changes endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SessionDep
from app.api.errors import ApiError
from app.api.pagination import DEFAULT_LIMIT, clamp_limit, decode_cursor, paginate
from app.api.schemas import (
    DocumentChangesOut,
    DocumentOut,
    Page,
    SnapshotChangeOut,
    SnapshotOut,
)
from app.canonical import service as canonical
from app.canonical.models import Document
from app.versioning import service as versioning
from app.versioning.service import DomainError

router = APIRouter(tags=["documents"])


def _get_document_or_404(session: Session, document_id: str) -> Document:
    document = session.get(Document, document_id)
    if document is None:
        raise ApiError(404, "not_found", f"document {document_id!r} not found")
    return document


def _document_out(document: Document) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        jurisdiction=document.jurisdiction,
        document_type=document.document_type,
        title=document.title,
        official_identifier=document.official_identifier,
        source_id=document.source_id,
        upstream_id=document.upstream_id,
        publication_date=document.publication_date,
        promulgation_date=document.promulgation_date,
        status=document.status,
        metadata=document.meta,
    )


@router.get("/documents", response_model=Page)
def list_documents(
    session: SessionDep,
    jurisdiction: str | None = None,
    document_type: str | None = None,
    source_id: str | None = None,
    q: str | None = Query(None, description="case-insensitive title substring"),
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> Page:
    limit = clamp_limit(limit)
    statement = select(Document).order_by(Document.id)
    if jurisdiction:
        statement = statement.where(Document.jurisdiction == jurisdiction)
    if document_type:
        statement = statement.where(Document.document_type == document_type)
    if source_id:
        statement = statement.where(Document.source_id == source_id)
    if q:
        statement = statement.where(Document.title.ilike(f"%{q}%"))
    documents = list(session.scalars(statement))
    page = paginate(documents, decode_cursor(cursor), limit)
    page["items"] = [_document_out(d) for d in page["items"]]
    return Page(**page)


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, session: SessionDep) -> DocumentOut:
    return _document_out(_get_document_or_404(session, document_id))


@router.get("/documents/{document_id}/tree")
def get_document_tree(document_id: str, session: SessionDep) -> dict:
    document = _get_document_or_404(session, document_id)
    return canonical.build_tree(session, document)


@router.get("/documents/{document_id}/versions")
def list_document_snapshots(document_id: str, session: SessionDep) -> dict:
    """Document snapshots: the ingestion runs (import batches) that grouped
    the node versions observed in each upstream release."""
    _get_document_or_404(session, document_id)
    try:
        runs = versioning.snapshot_runs_for_document(session, document_id)
    except DomainError as exc:
        raise ApiError(400, exc.code, str(exc)) from exc
    items = []
    for run in runs:
        items.append(
            SnapshotOut(
                snapshot_id=run.id,
                run_id=run.id,
                source_id=run.source_id,
                upstream_release_id=run.upstream_release_id,
                retrieved_at=run.retrieved_at,
                completed_at=run.completed_at,
                status=run.status,
                raw_artifact_uri=run.raw_artifact_uri,
                checksum=run.checksum,
                report=run.report,
            )
        )
    return {"items": items, "next_cursor": None, "has_more": False}


@router.get("/documents/{document_id}/changes", response_model=DocumentChangesOut)
def document_changes(
    document_id: str,
    session: SessionDep,
    from_snapshot_id: str = Query(alias="from"),
    to_snapshot_id: str = Query(alias="to"),
) -> DocumentChangesOut:
    """Structural change listing between two document snapshots (runs)."""
    _get_document_or_404(session, document_id)
    try:
        result = versioning.document_changes(
            session, document_id, from_snapshot_id, to_snapshot_id
        )
    except DomainError as exc:
        status = 404 if exc.code == "not_found" else 400
        raise ApiError(status, exc.code, str(exc)) from exc
    result["changes"] = [SnapshotChangeOut(**c) for c in result["changes"]]
    return DocumentChangesOut(**result)
