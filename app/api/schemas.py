"""Pydantic response schemas mirroring docs/spec/openapi.yaml."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class SourceOut(BaseModel):
    id: str
    name: str
    publisher: str | None = None
    jurisdiction: str
    source_type: str
    base_uri: str | None = None
    licence_name: str | None = None
    licence_uri: str | None = None
    created_at: datetime | None = None


class DocumentOut(BaseModel):
    id: str
    jurisdiction: str
    document_type: str
    title: str
    official_identifier: str | None = None
    source_id: str
    upstream_id: str | None = None
    publication_date: date | None = None
    promulgation_date: date | None = None
    status: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NodeOut(BaseModel):
    id: str
    document_id: str
    parent_id: str | None = None
    node_type: str
    label: str | None = None
    identifier: str | None = None
    sort_order: int
    upstream_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NodeVersionSummary(BaseModel):
    id: str
    node_id: str
    content_hash: str
    valid_from: date | None = None
    valid_to: date | None = None
    published_at: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    ingested_at: datetime


class Provenance(BaseModel):
    source_id: str
    upstream_version_id: str | None = None
    node_upstream_id: str | None = None
    source_uri: str | None = None
    ingestion_run_id: str
    upstream_release_id: str | None = None
    raw_artifact_uri: str | None = None


class NodeVersionOut(NodeVersionSummary):
    source_id: str
    ingestion_run_id: str
    upstream_version_id: str | None = None
    content: str
    content_format: str
    representation_id: str
    valid_from: date | None = None
    valid_to: date | None = None
    published_at: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    provenance: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


class Page(BaseModel):
    items: list[Any]
    next_cursor: str | None = None
    has_more: bool = False


class FragmentOut(BaseModel):
    version_id: str
    representation_id: str
    offset_unit: str
    start: int
    end: int
    text: str
    content_length: int


class ChangeOut(BaseModel):
    operation: str
    old_start: int | None = None
    old_end: int | None = None
    new_start: int | None = None
    new_end: int | None = None
    old_text: str | None = None
    new_text: str | None = None


class NodeDiffOut(BaseModel):
    node_id: str
    from_version_id: str
    to_version_id: str
    algorithm: str
    representation_id: str
    offset_unit: str
    changes: list[ChangeOut]
    content_hash: dict[str, str]
    source_provenance: dict[str, dict[str, Any]]
    is_legal_interpretation: bool = False


class SnapshotChangeOut(BaseModel):
    operation: str
    node_id: str
    from_version_id: str | None = None
    to_version_id: str | None = None


class DocumentChangesOut(BaseModel):
    document_id: str
    from_snapshot_id: str
    to_snapshot_id: str
    algorithm: str
    changes: list[SnapshotChangeOut]
    is_legal_interpretation: bool = False


class SnapshotOut(BaseModel):
    """A document snapshot = one ingestion run (import batch) that grouped
    the node versions observed in one upstream release."""

    snapshot_id: str
    run_id: str
    source_id: str
    upstream_release_id: str | None = None
    retrieved_at: datetime | None = None
    completed_at: datetime | None = None
    status: str
    raw_artifact_uri: str | None = None
    checksum: str | None = None
    report: dict[str, Any] = Field(default_factory=dict)
