"""Ingestion orchestration for Legilux acts (Luxembourg Journal officiel).

Fetches are done by content negotiation on the ELI URIs documented in
docs/legilux-feasibility.md:
- original act     : GET {ELI}          Accept: application/xml
- consolidated act : GET {ELI}/consolide Accept: application/xml
- act metadata    : GET {ELI} or {ELI}/consolide  Accept: text/turtle
"""

from __future__ import annotations

import urllib.request
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.canonical.service import DomainError
from app.core import sha256_hex
from app.db.base import utcnow
from app.ingestion.legilux_adapter import (
    ATTRIBUTION_TEMPLATE,
    AUTHORITY_NOTE,
    LEGILUX_BASE,
    LEGILUX_SOURCE,
    import_legilux_act,
    relink_legilux_references,
)
from app.sources.models import IngestionRun, Source
from app.storage import ObjectStore

USER_AGENT = "legal-git/0.1 (Legilux ingestion; contact: operator)"
FETCH_TIMEOUT = 60


def fetch(url: str, accept: str) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
        return response.read()


def act_urls(eli_path: str, variant: str) -> dict[str, str]:
    """eli_path: 'etat/leg/loi/1993/04/05/n1/jo' (no base, no leading /).
    A leading 'eli/' is accepted and normalized away."""
    path = eli_path.strip("/")
    if path.startswith("eli/"):
        path = path.removeprefix("eli/")
    base = f"{LEGILUX_BASE}/eli/{path}"
    suffix = "/consolide" if variant == "consolidated" else ""
    return {
        "xml": f"{base}{suffix}",
        "turtle": f"{base}{suffix}",
    }


def legilux_run_id_for(
    source_id: str, eli_path: str, variant: str, digest: str
) -> str:
    material = f"{source_id}\x1f{eli_path}\x1f{variant}\x1f{digest}"
    return f"run:{sha256_hex(material)[:32]}"


def import_legilux_release(
    session: Session,
    *,
    source: Source,
    eli_path: str,
    variant: str,
    store: ObjectStore,
    release_label: str | None = None,
    xml_file: Path | None = None,
    turtle_file: Path | None = None,
    retrieved_at: datetime | None = None,
) -> tuple[IngestionRun, bool]:
    """Imports one Legilux act variant. Returns (run, replayed).

    Idempotent: the run identity is the digest of the fetched artifact;
    a byte-identical fetch replays without creating anything. `xml_file` /
    `turtle_file` bypass the network (tests, offline replays).
    """
    variant_label = {"original": "texte d'origine", "consolidated": "texte consolidé"}[variant]
    release_label = release_label or f"{eli_path.strip('/')}|{variant}"
    urls = act_urls(eli_path, variant)

    if xml_file is not None:
        xml_bytes = Path(xml_file).read_bytes()
    else:
        xml_bytes = fetch(urls["xml"], "application/xml")
    if turtle_file is not None:
        turtle_text = Path(turtle_file).read_text(encoding="utf-8")
    elif xml_file is not None:
        turtle_text = None  # offline XML-only mode (documented degradation)
    else:
        try:
            turtle_text = fetch(urls["turtle"], "text/turtle").decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - metadata enrichment is optional
            turtle_text = None

    xml_text = xml_bytes.decode("utf-8")
    checksum = f"sha256:{sha256_hex(xml_text)}"
    run_id = legilux_run_id_for(source.id, eli_path, variant, checksum.removeprefix("sha256:"))

    # Referential linking runs on every call (replays included): an act
    # imported earlier may now resolve references other acts pointed at.
    resolved = relink_legilux_references(session)

    existing = session.get(IngestionRun, run_id)
    if existing is not None:
        return existing, True

    # Raw artifact retention: everything fetched, verbatim (guarded).
    artifact_key = f"raw/legilux-{sha256_hex(xml_bytes)[:40]}.xml"
    raw_artifact_uri = store.put(artifact_key, xml_bytes)
    if turtle_text is not None:
        store.put(
            f"raw/legilux-{sha256_hex(turtle_text.encode('utf-8'))[:40]}.ttl",
            turtle_text.encode("utf-8"),
        )

    run = IngestionRun(
        id=run_id,
        source_id=source.id,
        upstream_release_id=release_label,
        retrieved_at=retrieved_at or utcnow(),
        started_at=utcnow(),
        status="running",
        raw_artifact_uri=raw_artifact_uri,
        checksum=checksum,
        report={},
    )
    session.add(run)
    session.flush()

    document_id, report = import_legilux_act(
        session,
        source_id=source.id,
        xml_text=xml_text,
        turtle_text=turtle_text,
        variant=variant,
        ingestion_run_id=run.id,
        release_label=release_label,
    )
    # The just-imported act may itself be the target of references emitted
    # by earlier imports: resolve them now (relink is also run above, for
    # the replay path).
    resolved_end = relink_legilux_references(session)
    report.update(
        {
            "document_id": document_id,
            "eli_path": eli_path.strip("/"),
            "variant": variant,
            "variant_label": variant_label,
            "relationships_resolved": resolved + resolved_end,
            "fetch_urls": urls,
            "raw_artifact_uri": raw_artifact_uri,
            "raw_artifact_bytes": len(xml_bytes),
            "turtle_available": turtle_text is not None,
            "base_uri": LEGILUX_SOURCE["base_uri"],
            "licence": LEGILUX_SOURCE["licence_name"],
            "attribution": ATTRIBUTION_TEMPLATE.format(
                eli_path="/" + eli_path.strip("/") + ("/consolide" if variant == "consolidated" else ""),
                variant=variant_label,
            ),
            "authority_note": AUTHORITY_NOTE,
        }
    )
    run.report = report
    run.status = "completed"
    run.completed_at = utcnow()
    return run, False
