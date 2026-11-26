"""Acceptance criteria A: ingestion and provenance."""

from __future__ import annotations

from sqlalchemy import select

from app.canonical.models import IdentityMapping, Node, NodeVersion, Relationship
from app.core import sha256_hex
from tests.conftest import DOC_ID, NODE_1103, RELEASE_1, RELEASE_2, import_release


def test_run_identifies_source_and_retrieval_time(session, source, store):
    run, _ = import_release(session, source, RELEASE_1, store)
    assert run.source_id == source.id
    assert run.retrieved_at is not None
    assert run.started_at is not None
    assert run.completed_at is not None
    assert run.status == "completed"
    assert run.upstream_release_id == "demo-release-2024-06"


def test_raw_artifact_is_retained_with_checksum(session, source, store):
    xml = RELEASE_1.read_bytes()
    run, _ = import_release(session, source, RELEASE_1, store)
    assert run.checksum == f"sha256:{sha256_hex(xml)}"
    assert run.raw_artifact_uri.startswith("storage://raw/")
    retained = store.get(run.raw_artifact_uri.removeprefix("storage://"))
    assert retained == xml  # byte-for-byte retention


def test_upstream_identifiers_are_preserved(session, source, store):
    import_release(session, source, RELEASE_1, store)
    node = session.get(Node, NODE_1103)
    assert node.upstream_id == "fr:cc:article:1103"
    mapping = session.scalars(
        select(IdentityMapping).where(
            IdentityMapping.entity_type == "node",
            IdentityMapping.upstream_id == "fr:cc:article:1103",
        )
    ).first()
    assert mapping is not None
    assert mapping.canonical_id == NODE_1103
    assert mapping.source_id == source.id


def test_import_report_counts(session, source, store):
    run, _ = import_release(session, source, RELEASE_1, store)
    counts = run.report["counts"]
    # 6 nodes: livre, titre, articles 1103, 1104, 1105, 9999 (demo).
    assert counts["nodes_created"] == 6
    assert counts["versions_created"] == 4
    assert counts["relationships_created"] == 1
    assert counts["documents_created"] == 1
    assert run.report["errors"] == []


def test_second_release_reimports_unchanged_articles(session, source, store):
    run1, _ = import_release(session, source, RELEASE_1, store)
    run2, _ = import_release(session, source, RELEASE_2, store)
    counts = run2.report["counts"]
    # Livre, titre, 1103, 1104, 1105 already known -> unchanged.
    assert counts["nodes_created"] == 1  # article 1101
    assert counts["nodes_unchanged"] == 5
    # 1103 and 1105 are byte-identical re-observations: no new versions.
    assert counts["versions_created"] == 2  # 1101 (new node) and 1104 (changed)
    assert counts["versions_unchanged"] == 2
    # The relationship is a duplicate re-observation -> deduplicated.
    assert counts["relationships_created"] == 0
    assert counts["relationships_unchanged"] == 1


def test_idempotent_replay_creates_nothing(session, source, store):
    run1, _ = import_release(session, source, RELEASE_1, store)
    run_replay, replayed = import_release(session, source, RELEASE_1, store)
    assert replayed is True
    assert run_replay.id == run1.id
    run_replay2, replayed2 = import_release(session, source, RELEASE_1, store)
    assert replayed2 is True and run_replay2.id == run1.id

    nodes = list(session.scalars(select(Node).where(Node.document_id == DOC_ID)))
    versions = list(session.scalars(select(NodeVersion)))
    relationships = list(session.scalars(select(Relationship)))
    assert len(nodes) == 6
    assert len(versions) == 4
    assert len(relationships) == 1


def test_bad_package_is_rejected_with_code(session, source, store):
    from app.ingestion.service import IngestionError

    try:
        import_release_bytes_wrapped(session, source, store, b"<not-legal-git/>")
        raise AssertionError("expected IngestionError")
    except IngestionError as exc:
        assert exc.code == "parse_error"


def import_release_bytes_wrapped(session, source, store, xml: bytes):
    from app.ingestion.service import import_release_bytes

    run, _ = import_release_bytes(session, source=source, xml=xml, store=store)
    return run
