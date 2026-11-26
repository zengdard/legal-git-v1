"""Ingestion orchestration for LEGI (DILA open data) corpus textes."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.canonical.service import DomainError
from app.core import sha256_hex
from app.db.base import utcnow
from app.ingestion.legi_adapter import (
    ATTRIBUTION_TEMPLATE,
    LEGI_SOURCE,
    _pack_tree,
    corpus_manifest,
    find_texte_root,
    import_legi_texte,
)
from app.sources.models import IngestionRun, Source
from app.storage import ObjectStore


def legi_run_id_for(source_id: str, texte_cid: str, release_label: str, digest: str) -> str:
    material = f"{source_id}\x1f{texte_cid}\x1f{release_label}\x1f{digest}"
    return f"run:{sha256_hex(material)[:32]}"


def import_legi_release(
    session: Session,
    *,
    source: Source,
    texte_cid: str,
    base_dir: Path,
    release_label: str,
    store: ObjectStore,
    retrieved_at: datetime | None = None,
) -> tuple[IngestionRun, bool]:
    """Imports one LEGI texte from an extracted stock/daily directory.

    Returns (run, replayed). Idempotent: the deterministic corpus digest
    decides the run identity; a byte-identical corpus replays without
    creating anything.
    """
    texte_root = find_texte_root(base_dir, texte_cid)
    if texte_root is None:
        raise DomainError(
            "legi_texte_not_found",
            f"no extracted subtree for {texte_cid} under {base_dir}",
        )

    digest, file_count = corpus_manifest(texte_root)
    run_id = legi_run_id_for(source.id, texte_cid, release_label, digest)

    existing = session.get(IngestionRun, run_id)
    if existing is not None:
        return existing, True

    artifact_bytes = _pack_tree(texte_root)
    artifact_key = f"raw/{sha256_hex(artifact_bytes)[:40]}-{texte_cid}.tar.gz"
    raw_artifact_uri = store.put(artifact_key, artifact_bytes)

    run = IngestionRun(
        id=run_id,
        source_id=source.id,
        upstream_release_id=f"{release_label}|{texte_cid}",
        retrieved_at=retrieved_at or utcnow(),
        started_at=utcnow(),
        status="running",
        raw_artifact_uri=raw_artifact_uri,
        checksum=f"sha256:{digest}",
        report={},
    )
    session.add(run)
    session.flush()

    report = import_legi_texte(
        session,
        source_id=source.id,
        texte_cid=texte_cid,
        texte_root=texte_root,
        release_label=release_label,
        store=store,
        ingestion_run_id=run.id,
        retrieved_at=run.retrieved_at,
    )
    report.update(
        {
            "texte_cid": texte_cid,
            "upstream_stock": release_label,
            "corpus_files": file_count,
            "corpus_manifest_sha256": f"sha256:{digest}",
            "raw_artifact_uri": raw_artifact_uri,
            "raw_artifact_bytes": len(artifact_bytes),
            "base_uri": LEGI_SOURCE["base_uri"],
            "licence": LEGI_SOURCE["licence_name"],
            "attribution": ATTRIBUTION_TEMPLATE.format(label=release_label),
            # Official source remains authoritative:
            "authority_note": (
                "Légifrance (https://www.legifrance.gouv.fr) demeure la "
                "source authentique de publication ; ces données en sont "
                "une représentation technique normalisée."
            ),
        }
    )
    run.report = report
    run.status = "completed"
    run.completed_at = utcnow()
    return run, False
