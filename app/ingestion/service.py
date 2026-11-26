"""Ingestion orchestration: idempotent import runs with provenance.

Contract (acceptance criteria A):
- an ingestion run identifies its source and retrieval time;
- the raw source artifact is retained (storage abstraction) or the
  limitation is reported;
- re-running the same source release is idempotent: it maps back onto the
  same run and the same canonical entities and versions;
- the import report records counts, failures and skipped/unsupported
  records.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import CoreError, parse_corpus_xml, sha256_hex
from app.db.base import utcnow
from app.ingestion.xml_adapter import import_release, make_store
from app.sources.models import IngestionRun, Source
from app.storage import LocalFilesystemStore, ObjectStore


def run_id_for(source_id: str, upstream_release_id: str, checksum: str) -> str:
    digest = sha256_hex(f"{source_id}\x1f{upstream_release_id}\x1f{checksum}")
    return f"run:{digest[:32]}"


def import_release_bytes(
    session: Session,
    *,
    source: Source,
    xml: bytes,
    store: ObjectStore | None = None,
    retrieved_at: datetime | None = None,
) -> tuple[IngestionRun, bool]:
    """Imports one corpus release. Returns (run, replayed).

    The whole import (run record, nodes, versions, relationships) is atomic
    within the caller's transaction/session. `replayed` is True when the
    exact same release (same upstream release id and byte-identical
    artifact) had already been imported: nothing is re-created.
    """
    store = store or make_store()
    checksum = f"sha256:{sha256_hex(xml)}"
    retrieved_at = retrieved_at or utcnow()

    try:
        parsed = parse_corpus_xml(xml.decode("utf-8"))
    except CoreError as exc:
        raise IngestionError("parse_error", f"invalid corpus package: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise IngestionError(
            "invalid_encoding", f"corpus package is not valid UTF-8: {exc}"
        ) from exc

    upstream_release_id = parsed["corpus"]["release_id"]
    run_id = run_id_for(source.id, upstream_release_id, checksum)

    existing = session.get(IngestionRun, run_id)
    if existing is not None:
        return existing, True

    # Retention of the raw artifact (documented limitation when not retained).
    artifact_key = LocalFilesystemStore.content_key(xml)
    raw_artifact_uri = store.put(artifact_key, xml)

    run = IngestionRun(
        id=run_id,
        source_id=source.id,
        upstream_release_id=upstream_release_id,
        retrieved_at=retrieved_at,
        started_at=utcnow(),
        status="running",
        raw_artifact_uri=raw_artifact_uri,
        checksum=checksum,
        report={},
    )
    session.add(run)
    session.flush()

    report = import_release(
        session,
        source_id=source.id,
        ingestion_run_id=run.id,
        raw_artifact_uri=raw_artifact_uri,
        parsed=parsed,
    )
    report["raw_artifact_uri"] = raw_artifact_uri
    run.report = report
    run.status = "completed"
    run.completed_at = utcnow()
    return run, False


class IngestionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def list_runs_for_source(session: Session, source_id: str) -> list[IngestionRun]:
    statement = (
        select(IngestionRun)
        .where(IngestionRun.source_id == source_id)
        .order_by(IngestionRun.started_at, IngestionRun.id)
    )
    return list(session.scalars(statement))
