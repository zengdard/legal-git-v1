"""initial canonical schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# jsonb on PostgreSQL (equality/hashing), plain JSON on SQLite.

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


JSONType = sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("publisher", sa.String(length=512), nullable=True),
        sa.Column("jurisdiction", sa.String(length=8), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("base_uri", sa.Text(), nullable=True),
        sa.Column("licence_name", sa.String(length=255), nullable=True),
        sa.Column("licence_uri", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("upstream_release_id", sa.String(length=255), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("raw_artifact_uri", sa.Text(), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("report", JSONType, nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.UniqueConstraint(
            "source_id", "upstream_release_id", "checksum", name="uq_run_release"
        ),
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("jurisdiction", sa.String(length=8), nullable=False),
        sa.Column("document_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("official_identifier", sa.String(length=255), nullable=True),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("upstream_id", sa.String(length=255), nullable=True),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("promulgation_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("metadata", JSONType, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
    )

    op.create_table(
        "nodes",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("document_id", sa.String(length=255), nullable=False),
        sa.Column("parent_id", sa.String(length=255), nullable=True),
        sa.Column("node_type", sa.String(length=64), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("identifier", sa.String(length=255), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("upstream_id", sa.String(length=255), nullable=True),
        sa.Column("metadata", JSONType, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["nodes.id"]),
        sa.UniqueConstraint(
            "document_id", "node_type", "identifier", name="uq_node_identity"
        ),
    )
    op.create_index(
        "ix_nodes_parent",
        "nodes",
        ["document_id", "parent_id", "sort_order", "id"],
    )

    op.create_table(
        "node_versions",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("node_id", sa.String(length=255), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("ingestion_run_id", sa.String(length=255), nullable=False),
        sa.Column("upstream_version_id", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_format", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("representation_id", sa.String(length=64), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload_uri", sa.Text(), nullable=True),
        sa.Column("metadata", JSONType, nullable=True),
        sa.ForeignKeyConstraint(["ingestion_run_id"], ["ingestion_runs.id"]),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
    )
    op.create_index(
        "ix_versions_node", "node_versions", ["node_id", "ingested_at"]
    )

    op.create_table(
        "node_version_observations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ingestion_run_id", sa.String(length=255), nullable=False),
        sa.Column("node_version_id", sa.String(length=255), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["ingestion_run_id"], ["ingestion_runs.id"]),
        sa.ForeignKeyConstraint(["node_version_id"], ["node_versions.id"]),
        sa.UniqueConstraint("ingestion_run_id", "node_version_id", name="uq_observation"),
    )

    op.create_table(
        "node_relationships",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("from_node_id", sa.String(length=255), nullable=True),
        sa.Column("from_document_id", sa.String(length=255), nullable=True),
        sa.Column("to_node_id", sa.String(length=255), nullable=True),
        sa.Column("to_document_id", sa.String(length=255), nullable=True),
        sa.Column("to_key", sa.String(length=255), nullable=True),
        sa.Column("relationship_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("metadata", JSONType, nullable=True),
        sa.ForeignKeyConstraint(["from_document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["from_node_id"], ["nodes.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.UniqueConstraint(
            "from_node_id", "relationship_type", "to_key", name="uq_relationship"
        ),
    )

    op.create_table(
        "identity_mappings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("canonical_id", sa.String(length=255), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("upstream_id", sa.String(length=255), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.UniqueConstraint(
            "source_id", "entity_type", "upstream_id", name="uq_identity_mapping"
        ),
    )


def downgrade() -> None:
    op.drop_table("identity_mappings")
    op.drop_table("node_relationships")
    op.drop_index("ix_versions_node", table_name="node_versions")
    op.drop_table("node_versions")
    op.drop_index("ix_nodes_parent", table_name="nodes")
    op.drop_table("nodes")
    op.drop_table("documents")
    op.drop_table("ingestion_runs")
    op.drop_table("sources")
