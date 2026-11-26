"""Canonical entities: Document, Node, NodeVersion, Relationship and the
upstream-to-canonical identity mapping.

Notes on naming: the Python attribute `meta` maps to the `metadata` column
(`metadata` is reserved by SQLAlchemy on the declarative base).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow
from app.sources.models import JSONType


class Document(Base):
    """A logical legal instrument (e.g. the Code civil), stable across
    versions. Never identified by its content."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    jurisdiction: Mapped[str] = mapped_column(String(8))
    document_type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    official_identifier: Mapped[str | None] = mapped_column(String(255))
    source_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("sources.id"), nullable=False
    )
    upstream_id: Mapped[str | None] = mapped_column(String(255))
    publication_date: Mapped[date | None] = mapped_column(Date)
    promulgation_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str | None] = mapped_column(String(64))
    meta: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Node(Base):
    """A structural element (division, article...) within one document.

    Identity is deterministic (document + type + identifier) and never
    derived from content: text changes create new versions, not new nodes.
    """

    __tablename__ = "nodes"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "node_type", "identifier", name="uq_node_identity"
        ),
        Index("ix_nodes_parent", "document_id", "parent_id", "sort_order", "id"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("documents.id"), nullable=False
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(255), ForeignKey("nodes.id")
    )
    node_type: Mapped[str] = mapped_column(String(64))
    label: Mapped[str | None] = mapped_column(Text)
    identifier: Mapped[str | None] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    upstream_id: Mapped[str | None] = mapped_column(String(255))
    meta: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class NodeVersion(Base):
    """Immutable content of a node in one observed source state.

    A new observed state (different content or source facts) is a new
    version; existing versions are never updated. Two distinct source facts
    may legitimately carry identical content (e.g., two LEGIARTI fiches):
    version identity is the deterministic fingerprint of ALL the source
    facts (see version_id), not the content hash alone.
    """

    __tablename__ = "node_versions"
    __table_args__ = (
        Index("ix_versions_node", "node_id", "ingested_at"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    node_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("nodes.id"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("sources.id"), nullable=False
    )
    ingestion_run_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("ingestion_runs.id"), nullable=False
    )
    upstream_version_id: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_format: Mapped[str] = mapped_column(String(64), default="plain_text")
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    representation_id: Mapped[str] = mapped_column(String(64))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    published_at: Mapped[date | None] = mapped_column(Date)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    raw_payload_uri: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)


class NodeVersionObservation(Base):
    """Records which versions an ingestion run observed, INCLUDING versions
    that already existed (re-observed unchanged content). This is what makes
    a document snapshot the set of node versions observed in one upstream
    release, not merely the versions newly created by the run."""

    __tablename__ = "node_version_observations"
    __table_args__ = (
        UniqueConstraint(
            "ingestion_run_id", "node_version_id", name="uq_observation"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ingestion_run_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("ingestion_runs.id"), nullable=False
    )
    node_version_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("node_versions.id"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Relationship(Base):
    """A non-hierarchical link (citation, reference...). Parent-child
    hierarchy lives on nodes.parent_id and is a distinct concept."""

    __tablename__ = "node_relationships"
    __table_args__ = (
        UniqueConstraint(
            "from_node_id", "relationship_type", "to_key", name="uq_relationship"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_node_id: Mapped[str | None] = mapped_column(
        String(255), ForeignKey("nodes.id")
    )
    from_document_id: Mapped[str | None] = mapped_column(
        String(255), ForeignKey("documents.id")
    )
    to_node_id: Mapped[str | None] = mapped_column(String(255))
    to_document_id: Mapped[str | None] = mapped_column(String(255))
    # Stable dedup key for the target when it is an external upstream
    # reference rather than a known node.
    to_key: Mapped[str | None] = mapped_column(String(255))
    relationship_type: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[str | None] = mapped_column(
        String(255), ForeignKey("sources.id")
    )
    evidence: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)


class IdentityMapping(Base):
    """Mapping between upstream identifiers and canonical IDs."""

    __tablename__ = "identity_mappings"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "entity_type", "upstream_id", name="uq_identity_mapping"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    canonical_id: Mapped[str] = mapped_column(String(255))
    source_id: Mapped[str] = mapped_column(String(255), ForeignKey("sources.id"))
    upstream_id: Mapped[str] = mapped_column(String(255))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
