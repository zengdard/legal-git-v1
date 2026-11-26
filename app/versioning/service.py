"""Versioning services: immutable version records, diffs, snapshots.

Immutability (acceptance criteria C) is enforced at every layer that can
touch NodeVersion rows:
- no service function updates versions;
- a SQLAlchemy event guard rejects ORM updates of NodeVersion rows;
- ingestion is idempotent: an identical source state maps onto the same
  version id and is never duplicated.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.canonical.models import Node, NodeVersion, NodeVersionObservation
from app.canonical.service import DomainError

try:  # V1-only builds (open-source engine) ship without the V2 outbox
    from app.v2.services_syntax import emit_source_event
except ImportError:  # pragma: no cover - exercised in the V1 dist builds
    emit_source_event = None

from app.core import (
    diff_text,
    fingerprint_of_version,
    make_version_id,
    sha256_hex,
)
from app.sources.models import IngestionRun, Source

REPRESENTATION_ID = "plain-text-v1"


def _immutable_guard(mapper, connection, target):
    raise DomainError(
        "version_immutable",
        f"node version {getattr(target, 'id', '?')!r} is immutable and "
        "cannot be updated; corrections must create a new version",
    )


def install_immutability_guard() -> None:
    """Rejects ORM-level UPDATE statements against node_versions."""
    event.listen(NodeVersion, "before_update", _immutable_guard)


_VERSION_IMMUTABLE_FIELDS = (
    "node_id",
    "source_id",
    "ingestion_run_id",
    "upstream_version_id",
    "content",
    "content_format",
    "content_hash",
    "representation_id",
    "valid_from",
    "valid_to",
    "published_at",
    "effective_from",
    "effective_to",
    "ingested_at",
    "raw_payload_uri",
)


def create_version(
    session: Session,
    *,
    node: Node,
    source_id: str,
    ingestion_run_id: str,
    content: str,
    content_format: str = "plain_text",
    upstream_version_id: str | None = None,
    valid_from: date | None = None,
    valid_to: date | None = None,
    published_at: date | None = None,
    effective_from: date | None = None,
    effective_to: date | None = None,
    raw_payload_uri: str | None = None,
    meta: dict | None = None,
    representation_id: str = REPRESENTATION_ID,
) -> tuple[NodeVersion, bool]:
    """Idempotent creation of one immutable node version."""
    fingerprint = fingerprint_of_version(
        content_format=content_format,
        content=content,
        upstream_version_id=upstream_version_id,
        valid_from=valid_from.isoformat() if valid_from else None,
        valid_to=valid_to.isoformat() if valid_to else None,
        published_at=published_at.isoformat() if published_at else None,
        effective_from=effective_from.isoformat() if effective_from else None,
        effective_to=effective_to.isoformat() if effective_to else None,
    )
    version_id = make_version_id(node.id, fingerprint)

    validate_dates(valid_from, valid_to, effective_from, effective_to)

    existing = session.get(NodeVersion, version_id)
    if existing is not None:
        return existing, False

    version = NodeVersion(
        id=version_id,
        node_id=node.id,
        source_id=source_id,
        ingestion_run_id=ingestion_run_id,
        upstream_version_id=upstream_version_id,
        content=content,
        content_format=content_format,
        content_hash=f"sha256:{sha256_hex(content)}",
        representation_id=representation_id,
        valid_from=valid_from,
        valid_to=valid_to,
        published_at=published_at,
        effective_from=effective_from,
        effective_to=effective_to,
        raw_payload_uri=raw_payload_uri,
        meta=meta or {},
    )
    session.add(version)
    session.flush()

    # V2 transactional outbox (additive): one event per created node
    # version, in the same transaction as the ingestion. The V1-only
    # builds (open-source engine) have no V2 layer: the outbox simply
    # does not exist there.
    if emit_source_event is not None:
        emit_source_event(
            session, version=version, ingestion_run_id=ingestion_run_id
        )
    return version, True


def validate_dates(
    valid_from: date | None,
    valid_to: date | None,
    effective_from: date | None,
    effective_to: date | None,
) -> None:
    if valid_from and valid_to and valid_to < valid_from:
        raise DomainError(
            "invalid_dates", "valid_to must not be before valid_from"
        )
    if effective_from and effective_to and effective_to < effective_from:
        raise DomainError(
            "invalid_dates", "effective_to must not be before effective_from"
        )


def observe_version(session: Session, *, ingestion_run_id: str, version_id: str) -> None:
    """Records that an ingestion run observed a version (idempotent)."""
    from app.canonical.models import NodeVersionObservation

    existing = session.scalars(
        select(NodeVersionObservation).where(
            NodeVersionObservation.ingestion_run_id == ingestion_run_id,
            NodeVersionObservation.node_version_id == version_id,
        )
    ).first()
    if existing is not None:
        return
    session.add(
        NodeVersionObservation(
            ingestion_run_id=ingestion_run_id, node_version_id=version_id
        )
    )


def list_versions(session: Session, node_id: str) -> list[NodeVersion]:
    """History order: chronological by validity start (undated versions
    last, then deterministic by version id)."""
    statement = (
        select(NodeVersion)
        .where(NodeVersion.node_id == node_id)
        .order_by(
            NodeVersion.valid_from.asc().nulls_last(),
            NodeVersion.id,
        )
    )
    return list(session.scalars(statement))


def get_version(session: Session, version_id: str) -> NodeVersion | None:
    return session.get(NodeVersion, version_id)


def verify_content_integrity(version: NodeVersion) -> None:
    """The stored content must still hash to the recorded content hash."""
    actual = f"sha256:{sha256_hex(version.content)}"
    if actual != version.content_hash:
        raise DomainError(
            "content_hash_mismatch",
            f"version {version.id!r} no longer matches its recorded content hash",
        )


def diff_versions(session: Session, from_id: str, to_id: str) -> dict[str, Any]:
    """Textual diff between two explicit versions of the same node."""
    from_version = session.get(NodeVersion, from_id)
    to_version = session.get(NodeVersion, to_id)
    if from_version is None or to_version is None:
        raise DomainError("not_found", "one of the versions does not exist")
    if from_version.node_id != to_version.node_id:
        raise DomainError(
            "version_node_mismatch",
            "versions do not belong to the same node",
        )
    if from_version.representation_id != to_version.representation_id:
        raise DomainError(
            "representation_mismatch",
            f"cannot diff representations {from_version.representation_id!r} "
            f"and {to_version.representation_id!r}; compared versions must "
            "share the exact content representation",
        )
    verify_content_integrity(from_version)
    verify_content_integrity(to_version)

    result = diff_text(from_version.content, to_version.content)
    node = session.get(Node, from_version.node_id)
    source_ids = {from_version.source_id, to_version.source_id}
    sources = {s.id: s for s in session.scalars(select(Source).where(Source.id.in_(source_ids)))}
    runs = {
        r.id: r
        for r in session.scalars(
            select(IngestionRun).where(
                IngestionRun.id.in_({from_version.ingestion_run_id, to_version.ingestion_run_id})
            )
        )
    }

    return {
        "node_id": from_version.node_id,
        "from_version_id": from_version.id,
        "to_version_id": to_version.id,
        "algorithm": result["algorithm"],
        "representation_id": from_version.representation_id,
        "offset_unit": result["offset_unit"],
        "changes": result["changes"],
        "content_hash": {
            "from": from_version.content_hash,
            "to": to_version.content_hash,
        },
        "source_provenance": {
            "from": _provenance(from_version, sources, runs, node),
            "to": _provenance(to_version, sources, runs, node),
        },
        # A diff is a textual/structural change record between two explicit
        # versions. It is not a legal interpretation or impact assessment.
        "is_legal_interpretation": False,
    }


def _provenance(
    version: NodeVersion,
    sources: dict[str, Source],
    runs: dict[str, IngestionRun],
    node: Node | None,
) -> dict[str, Any]:
    source = sources.get(version.source_id)
    run = runs.get(version.ingestion_run_id)
    return {
        "source_id": version.source_id,
        "upstream_version_id": version.upstream_version_id,
        "node_upstream_id": node.upstream_id if node else None,
        "source_uri": source.base_uri if source else None,
        "ingestion_run_id": version.ingestion_run_id,
        "upstream_release_id": run.upstream_release_id if run else None,
        "raw_artifact_uri": run.raw_artifact_uri if run else None,
        "ingested_at": version.ingested_at.isoformat(),
    }


def snapshot_runs_for_document(session: Session, document_id: str) -> list[IngestionRun]:
    """Ingestion runs (import batches / snapshots) that touched a document,
    oldest first. Each run groups the node versions observed together in one
    upstream release (including re-observed unchanged versions)."""
    run_ids = (
        select(NodeVersionObservation.ingestion_run_id)
        .join(NodeVersion, NodeVersion.id == NodeVersionObservation.node_version_id)
        .join(Node, Node.id == NodeVersion.node_id)
        .where(Node.document_id == document_id)
        .distinct()
    )
    statement = (
        select(IngestionRun)
        .where(IngestionRun.id.in_(run_ids))
        .order_by(IngestionRun.started_at, IngestionRun.id)
    )
    return list(session.scalars(statement))


def document_changes(
    session: Session, document_id: str, from_run_id: str, to_run_id: str
) -> dict[str, Any]:
    """Structural change listing between two document snapshots (runs).

    node_added / node_removed / node_changed operations, driven by the set of
    node versions observed in each run. No legal effect is inferred."""
    runs = (
        session.get(IngestionRun, from_run_id),
        session.get(IngestionRun, to_run_id),
    )
    if any(r is None for r in runs):
        raise DomainError("not_found", "one of the snapshot runs does not exist")

    def versions_of(run_id: str) -> dict[str, NodeVersion]:
        statement = (
            select(NodeVersion)
            .join(
                NodeVersionObservation,
                NodeVersionObservation.node_version_id == NodeVersion.id,
            )
            .join(Node, Node.id == NodeVersion.node_id)
            .where(Node.document_id == document_id)
            .where(NodeVersionObservation.ingestion_run_id == run_id)
        )
        return {v.node_id: v for v in session.scalars(statement)}

    from_versions = versions_of(from_run_id)
    to_versions = versions_of(to_run_id)
    if not from_versions and not to_versions:
        raise DomainError(
            "snapshot_document_mismatch",
            "neither snapshot contains versions of this document",
        )

    changes: list[dict[str, Any]] = []
    for node_id in sorted(from_versions.keys() - to_versions.keys()):
        changes.append(
            {
                "operation": "node_removed",
                "node_id": node_id,
                "from_version_id": from_versions[node_id].id,
                "to_version_id": None,
            }
        )
    for node_id in sorted(to_versions.keys() - from_versions.keys()):
        changes.append(
            {
                "operation": "node_added",
                "node_id": node_id,
                "from_version_id": None,
                "to_version_id": to_versions[node_id].id,
            }
        )
    for node_id in sorted(from_versions.keys() & to_versions.keys()):
        old, new = from_versions[node_id], to_versions[node_id]
        if old.content_hash != new.content_hash:
            changes.append(
                {
                    "operation": "node_changed",
                    "node_id": node_id,
                    "from_version_id": old.id,
                    "to_version_id": new.id,
                }
            )

    return {
        "document_id": document_id,
        "from_snapshot_id": from_run_id,
        "to_snapshot_id": to_run_id,
        "algorithm": "document-snapshot-diff-v1",
        "changes": changes,
        # Structural/textual change record between two document snapshots;
        # not a statement of legal effect.
        "is_legal_interpretation": False,
    }
