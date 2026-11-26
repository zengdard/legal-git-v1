"""Nodes, node versions, version diffs, and version-scoped fragments."""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from app.api.deps import SessionDep
from app.api.errors import ApiError
from app.api.pagination import DEFAULT_LIMIT, clamp_limit, decode_cursor, paginate
from app.api.schemas import (
    FragmentOut,
    NodeDiffOut,
    NodeOut,
    NodeVersionOut,
    NodeVersionSummary,
    Page,
)
from app.canonical import service as canonical
from app.canonical.models import Node, NodeVersion
from app.core import CoreError, extract_fragment
from app.sources.models import IngestionRun, Source
from app.versioning import service as versioning
from app.versioning.service import DomainError

router = APIRouter(tags=["nodes"])


def _get_node_or_404(session: Session, node_id: str) -> Node:
    node = session.get(Node, node_id)
    if node is None:
        raise ApiError(404, "not_found", f"node {node_id!r} not found")
    return node


def _node_out(node: Node) -> NodeOut:
    return NodeOut(
        id=node.id,
        document_id=node.document_id,
        parent_id=node.parent_id,
        node_type=node.node_type,
        label=node.label,
        identifier=node.identifier,
        sort_order=node.sort_order,
        upstream_id=node.upstream_id,
        metadata=node.meta,
    )


def _version_summary(version: NodeVersion) -> NodeVersionSummary:
    return NodeVersionSummary(
        id=version.id,
        node_id=version.node_id,
        content_hash=version.content_hash,
        valid_from=version.valid_from,
        valid_to=version.valid_to,
        published_at=version.published_at,
        effective_from=version.effective_from,
        effective_to=version.effective_to,
        ingested_at=version.ingested_at,
    )


def _version_out(session: Session, version: NodeVersion) -> NodeVersionOut:
    source = session.get(Source, version.source_id)
    run = session.get(IngestionRun, version.ingestion_run_id)
    node = session.get(Node, version.node_id)
    return NodeVersionOut(
        id=version.id,
        node_id=version.node_id,
        source_id=version.source_id,
        ingestion_run_id=version.ingestion_run_id,
        upstream_version_id=version.upstream_version_id,
        content=version.content,
        content_format=version.content_format,
        representation_id=version.representation_id,
        content_hash=version.content_hash,
        valid_from=version.valid_from,
        valid_to=version.valid_to,
        published_at=version.published_at,
        effective_from=version.effective_from,
        effective_to=version.effective_to,
        ingested_at=version.ingested_at,
        provenance={
            "upstream_version_id": version.upstream_version_id,
            "node_upstream_id": node.upstream_id if node else None,
            "source_uri": source.base_uri if source else None,
            "ingestion_run_id": version.ingestion_run_id,
            "upstream_release_id": run.upstream_release_id if run else None,
            "raw_artifact_uri": run.raw_artifact_uri if run else None,
        },
        metadata=version.meta,
    )


@router.get("/nodes/{node_id}", response_model=NodeOut)
def get_node(node_id: str, session: SessionDep) -> NodeOut:
    return _node_out(_get_node_or_404(session, node_id))


@router.get("/nodes/{node_id}/children", response_model=Page)
def list_node_children(
    node_id: str,
    session: SessionDep,
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> Page:
    limit = clamp_limit(limit)
    _get_node_or_404(session, node_id)
    children = canonical.list_children(session, node_id)
    page = paginate(children, decode_cursor(cursor), limit)
    page["items"] = [_node_out(child) for child in page["items"]]
    return Page(**page)


@router.get("/nodes/{node_id}/versions", response_model=Page)
def list_node_versions(
    node_id: str,
    session: SessionDep,
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> Page:
    limit = clamp_limit(limit)
    _get_node_or_404(session, node_id)
    try:
        versions = versioning.list_versions(session, node_id)
    except DomainError as exc:
        raise ApiError(400, exc.code, str(exc)) from exc
    page = paginate(versions, decode_cursor(cursor), limit)
    page["items"] = [_version_summary(v) for v in page["items"]]
    return Page(**page)


@router.get("/nodes/{node_id}/versions/{version_id}", response_model=NodeVersionOut)
def get_node_version(
    node_id: str, version_id: str, session: SessionDep
) -> NodeVersionOut:
    _get_node_or_404(session, node_id)
    version = session.get(NodeVersion, version_id)
    if version is None or version.node_id != node_id:
        raise ApiError(
            404, "not_found", f"version {version_id!r} of node {node_id!r} not found"
        )
    try:
        versioning.verify_content_integrity(version)
    except DomainError as exc:
        raise ApiError(409, exc.code, str(exc)) from exc
    return _version_out(session, version)


@router.get("/nodes/{node_id}/diff", response_model=NodeDiffOut)
def diff_node_versions(
    node_id: str,
    session: SessionDep,
    from_version_id: str = Query(alias="from"),
    to_version_id: str = Query(alias="to"),
) -> NodeDiffOut:
    """Textual diff between two explicit versions of a node. The diff is a
    change record, not a legal interpretation or impact assessment."""
    _get_node_or_404(session, node_id)
    try:
        result = versioning.diff_versions(session, from_version_id, to_version_id)
    except DomainError as exc:
        if exc.code == "not_found":
            raise ApiError(404, exc.code, str(exc)) from exc
        raise ApiError(400, exc.code, str(exc)) from exc
    if result["node_id"] != node_id:
        raise ApiError(
            400,
            "version_node_mismatch",
            "the compared versions do not belong to this node",
        )
    return NodeDiffOut(**result)


@router.get("/node-versions/{version_id}/fragment", response_model=FragmentOut)
def get_fragment(
    version_id: str,
    session: SessionDep,
    start: int = Query(ge=0),
    end: int = Query(ge=0),
    representation: str = Query(description="must match the version representation"),
) -> FragmentOut:
    """Version-scoped fragment: [start, end) in the declared offset unit over
    the exact content of one specific node version."""
    version = session.get(NodeVersion, version_id)
    if version is None:
        raise ApiError(404, "not_found", f"node version {version_id!r} not found")
    if representation != version.representation_id:
        raise ApiError(
            400,
            "representation_mismatch",
            f"version {version_id!r} is published in representation "
            f"{version.representation_id!r}, not {representation!r}",
        )
    try:
        versioning.verify_content_integrity(version)
        fragment = extract_fragment(
            version.content, start, end, "unicode_code_point"
        )
    except DomainError as exc:
        raise ApiError(409, exc.code, str(exc)) from exc
    except CoreError as exc:
        raise ApiError(400, exc.code, str(exc)) from exc
    return FragmentOut(
        version_id=version_id,
        representation_id=version.representation_id,
        offset_unit=fragment["offset_unit"],
        start=fragment["start"],
        end=fragment["end"],
        text=fragment["text"],
        content_length=fragment["content_length"],
    )
