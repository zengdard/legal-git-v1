"""Bulk corpus export: deterministic NDJSON generation (docs/exports.md)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.canonical.models import Document, Node, NodeVersion, Relationship
from app.sources.models import Source


def _line(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True)


def export_document_records(session: Session, document: Document) -> list[dict[str, Any]]:
    """All export records of one corpus, in deterministic order."""
    source = session.get(Source, document.source_id)
    nodes = list(
        session.scalars(
            select(Node).where(Node.document_id == document.id).order_by(Node.id)
        )
    )
    versions = list(
        session.scalars(
            select(NodeVersion)
            .join(Node, Node.id == NodeVersion.node_id)
            .where(Node.document_id == document.id)
            .order_by(NodeVersion.node_id, NodeVersion.ingested_at, NodeVersion.id)
        )
    )
    relationships = list(
        session.scalars(
            select(Relationship)
            .where(Relationship.from_document_id == document.id)
            .order_by(Relationship.id)
        )
    )

    def _iso(value) -> str | None:
        return value.isoformat() if value else None

    records: list[dict[str, Any]] = [
        {
            "type": "manifest",
            "format": "ndjson",
            "schema_version": 1,
            "document_id": document.id,
            "document_title": document.title,
            "jurisdiction": document.jurisdiction,
            "records": {
                "nodes": len(nodes),
                "node_versions": len(versions),
                "relationships": len(relationships),
            },
            "source_metadata": (
                {
                    "id": source.id,
                    "name": source.name,
                    "publisher": source.publisher,
                    "type": source.source_type,
                    "base_uri": source.base_uri,
                    "licence": source.licence_name,
                }
                if source
                else None
            ),
            "note": "Official publication sources remain authoritative; this "
            "export is a normalized technical representation with traceable "
            "provenance.",
        },
        {
            "type": "document",
            "id": document.id,
            "jurisdiction": document.jurisdiction,
            "document_type": document.document_type,
            "title": document.title,
            "official_identifier": document.official_identifier,
            "source_id": document.source_id,
            "upstream_id": document.upstream_id,
            "metadata": document.meta,
        },
    ]

    for node in nodes:
        records.append(
            {
                "type": "node",
                "id": node.id,
                "document_id": node.document_id,
                "parent_id": node.parent_id,
                "node_type": node.node_type,
                "label": node.label,
                "identifier": node.identifier,
                "sort_order": node.sort_order,
                "upstream_id": node.upstream_id,
                "metadata": node.meta,
            }
        )

    for version in versions:
        records.append(
            {
                "type": "node_version",
                "id": version.id,
                "node_id": version.node_id,
                "source_id": version.source_id,
                "ingestion_run_id": version.ingestion_run_id,
                "upstream_version_id": version.upstream_version_id,
                "content": version.content,
                "content_format": version.content_format,
                "content_hash": version.content_hash,
                "representation_id": version.representation_id,
                "valid_from": _iso(version.valid_from),
                "valid_to": _iso(version.valid_to),
                "published_at": _iso(version.published_at),
                "effective_from": _iso(version.effective_from),
                "effective_to": _iso(version.effective_to),
                "ingested_at": _iso(version.ingested_at),
            }
        )

    for relationship in relationships:
        records.append(
            {
                "type": "relationship",
                "id": f"rel:{relationship.id}",
                "from_node_id": relationship.from_node_id,
                "relationship_type": relationship.relationship_type,
                "to_node_id": relationship.to_node_id,
                "to_key": relationship.to_key,
                "evidence": relationship.evidence,
                "metadata": relationship.meta,
            }
        )
    return records


def build_ndjson(session: Session, document: Document) -> tuple[bytes, str]:
    """NDJSON payload of one corpus + its sha256 (returned in headers)."""
    payload = ("\n".join(_line(r) for r in export_document_records(session, document))
               + "\n").encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return payload, digest


def corpus_manifest(session: Session) -> list[dict[str, Any]]:
    """Export manifest items: one per document."""
    documents = list(session.scalars(select(Document).order_by(Document.id)))
    items = []
    for document in documents:
        node_count = len(
            list(
                session.scalars(
                    select(Node.id).where(Node.document_id == document.id)
                )
            )
        )
        version_count = len(
            list(
                session.scalars(
                    select(NodeVersion.id)
                    .join(Node, Node.id == NodeVersion.node_id)
                    .where(Node.document_id == document.id)
                )
            )
        )
        items.append(
            {
                "corpus_id": document.id,
                "document_id": document.id,
                "title": document.title,
                "jurisdiction": document.jurisdiction,
                "format": "ndjson",
                "records": {"nodes": node_count, "node_versions": version_count},
                "download": f"/v1/exports/{document.id}",
            }
        )
    return items
