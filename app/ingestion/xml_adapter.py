"""Corpus XML adapter: maps parsed source packages onto canonical entities.

This module is deliberately separate from the canonical model and services
(AGENTS.md: "keep ingestion adapters separate from the canonical data
model"). It consumes the neutral JSON produced by the C++ parser
(`legalgit_core.parse_corpus_xml`) and never invents facts that are absent
from the source: missing fields stay null and unknown source elements are
carried into the import report.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.canonical import service as canonical
from app.canonical.models import IdentityMapping, Relationship
from app.core import normalize_slug_component
from app.storage import LocalFilesystemStore, ObjectStore
from app.versioning import service as versioning
from app.versioning.service import DomainError

# Upstream lien types -> canonical relationship types, mirroring the mapping
# table in the C++ parser. Both sides are preserved.
LIEN_RELATIONSHIPS = {
    "cites": "cites",
    "related_to": "related_to",
    "repeals": "repeals",
    "amends": "amends",
    "refers_to": "refers_to",
    "implements": "implements",
}


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


class ImportReport:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {
            "documents_created": 0,
            "documents_unchanged": 0,
            "nodes_created": 0,
            "nodes_unchanged": 0,
            "versions_created": 0,
            "versions_unchanged": 0,
            "relationships_created": 0,
            "relationships_unchanged": 0,
            "skipped": 0,
        }
        self.errors: list[dict[str, str]] = []
        self.unsupported: list[dict[str, Any]] = []

    def error(self, where: str, code: str, message: str) -> None:
        self.counts["skipped"] += 1
        self.errors.append({"where": where, "code": code, "message": message})

    def to_dict(self, source_release: str) -> dict[str, Any]:
        return {
            "upstream_release_id": source_release,
            "counts": dict(self.counts),
            "errors": list(self.errors),
            "skipped_unsupported_elements": list(self.unsupported),
        }


def touch_identity_mapping(
    session: Session,
    *,
    entity_type: str,
    canonical_id: str,
    source_id: str,
    upstream_id: str,
) -> None:
    statement = select(IdentityMapping).where(
        IdentityMapping.entity_type == entity_type,
        IdentityMapping.source_id == source_id,
        IdentityMapping.upstream_id == upstream_id,
    )
    mapping = session.scalars(statement).first()
    if mapping is None:
        session.add(
            IdentityMapping(
                entity_type=entity_type,
                canonical_id=canonical_id,
                source_id=source_id,
                upstream_id=upstream_id,
            )
        )
    else:
        from app.db.base import utcnow

        mapping.last_seen_at = utcnow()


def import_release(
    session: Session,
    *,
    source_id: str,
    ingestion_run_id: str,
    raw_artifact_uri: str | None,
    parsed: dict[str, Any],
) -> dict[str, Any]:
    """Maps one parsed corpus release onto canonical entities.

    All or nothing within the caller's transaction: a structural failure
    aborts; per-record domain failures are skipped and recorded.
    """
    report = ImportReport()
    report.unsupported = list(parsed.get("unsupported", []))
    corpus = parsed["corpus"]

    document, document_created = canonical.get_or_create_document(
        session,
        source_id=source_id,
        jurisdiction=corpus["jurisdiction"],
        slug=corpus["slug"],
        title=corpus["title"],
        document_type=corpus.get("document_type") or "code",
        official_identifier=corpus.get("official_id"),
        upstream_id=corpus.get("official_id"),
        meta={
            "evidence": corpus["evidence"],
            "extra": corpus.get("extra") or {},
        },
    )
    if document_created:
        report.counts["documents_created"] += 1
        if corpus.get("official_id"):
            touch_identity_mapping(
                session,
                entity_type="document",
                canonical_id=document.id,
                source_id=source_id,
                upstream_id=corpus["official_id"],
            )
    else:
        report.counts["documents_unchanged"] += 1

    # Nodes arrive in document order, so parents are always mapped first.
    canonical_by_upstream: dict[str, str] = {}
    for record in parsed["nodes"]:
        upstream_id = record["upstream_id"]
        try:
            identifier = _node_identifier(record)
            node, node_created = canonical.get_or_create_node(
                session,
                document_id=document.id,
                node_type=record["node_type"],
                identifier=identifier,
                parent_id=canonical_by_upstream.get(record["upstream_parent_id"]),
                label=record.get("label"),
                sort_order=int(record.get("order", 0)),
                upstream_id=upstream_id,
                meta=dict(record.get("metadata") or {}, evidence=corpus["evidence"]),
            )
        except DomainError as exc:
            report.error(
                f"node {upstream_id}", exc.code, str(exc)
            )
            continue
        canonical_by_upstream[upstream_id] = node.id
        if node_created:
            report.counts["nodes_created"] += 1
            touch_identity_mapping(
                session,
                entity_type="node",
                canonical_id=node.id,
                source_id=source_id,
                upstream_id=upstream_id,
            )
        else:
            report.counts["nodes_unchanged"] += 1

    for record in parsed["versions"]:
        upstream_node_id = record["node_upstream_id"]
        node_id = canonical_by_upstream.get(upstream_node_id)
        if node_id is None:
            report.error(
                f"version of {upstream_node_id}",
                "orphan_version",
                "version references a node that was skipped or is missing",
            )
            continue
        node = canonical.get_node(session, node_id)
        try:
            version, created = versioning.create_version(
                session,
                node=node,
                source_id=source_id,
                ingestion_run_id=ingestion_run_id,
                content=record["content"],
                content_format=record.get("content_format") or "plain_text",
                upstream_version_id=record.get("upstream_version_id"),
                valid_from=_parse_date(record.get("valid_from")),
                valid_to=_parse_date(record.get("valid_to")),
                published_at=_parse_date(record.get("published_at")),
                effective_from=_parse_date(record.get("effective_from")),
                effective_to=_parse_date(record.get("effective_to")),
                raw_payload_uri=raw_artifact_uri,
                meta=dict(
                    record.get("metadata") or {},
                    evidence=corpus["evidence"],
                    **({"state": record["state"]} if record.get("state") else {}),
                ),
            )
        except DomainError as exc:
            report.error(
                f"version of {upstream_node_id}", exc.code, str(exc)
            )
            continue
        # The run observes the version whether it was just created or was
        # already known (re-observed unchanged content).
        versioning.observe_version(
            session, ingestion_run_id=ingestion_run_id, version_id=version.id
        )
        key = "versions_created" if created else "versions_unchanged"
        report.counts[key] += 1

    for record in parsed["relationships"]:
        from_node_id = canonical_by_upstream.get(record["from_node_upstream_id"])
        if from_node_id is None:
            report.error(
                f"relationship from {record['from_node_upstream_id']}",
                "orphan_relationship",
                "relationship references a node that was skipped or is missing",
            )
            continue
        relationship_type = record["relationship_type"]
        if relationship_type not in LIEN_RELATIONSHIPS:
            relationship_type = "related_to"
        upstream_target = record["target_upstream_id"]
        to_node_id = _resolve_target(session, source_id, upstream_target)
        to_key = to_node_id or f"{source_id}:{upstream_target}"
        statement = select(Relationship).where(
            Relationship.from_node_id == from_node_id,
            Relationship.relationship_type == relationship_type,
            Relationship.to_key == to_key,
        )
        existing = session.scalars(statement).first()
        if existing is not None:
            report.counts["relationships_unchanged"] += 1
            continue
        session.add(
            Relationship(
                from_node_id=from_node_id,
                from_document_id=document.id,
                to_node_id=to_node_id,
                to_document_id=None,
                to_key=to_key,
                relationship_type=relationship_type,
                source_id=source_id,
                evidence=record.get("description"),
                meta=dict(
                    record.get("metadata") or {},
                    upstream_type=record.get("upstream_type"),
                    upstream_target=upstream_target,
                ),
            )
        )

        report.counts["relationships_created"] += 1

    return report.to_dict(corpus["release_id"])


def _node_identifier(record: dict[str, Any]) -> str:
    """Deterministic node identifier from source facts (never from text)."""
    num = record.get("num")
    if num:
        return str(num)
    # Divisions without a number fall back to the slug of their label.
    return normalize_slug_component(record.get("label") or record["upstream_id"])


def _resolve_target(session: Session, source_id: str, upstream_target: str) -> str | None:
    """Resolves an upstream reference to a canonical node when known."""
    from app.canonical.models import IdentityMapping

    statement = select(IdentityMapping).where(
        IdentityMapping.entity_type == "node",
        IdentityMapping.source_id == source_id,
        IdentityMapping.upstream_id == upstream_target,
    )
    mapping = session.scalars(statement).first()
    return mapping.canonical_id if mapping else None


def make_store() -> ObjectStore:
    return LocalFilesystemStore()
