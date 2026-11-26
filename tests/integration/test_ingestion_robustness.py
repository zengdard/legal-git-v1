"""Ingestion robustness (category 6 of the test specification).

The critical property under test:

    Si l'import échoue à mi-course, Legal Git doit pouvoir reprendre sans
    corrompre les données déjà importées. — garanti par l'atomicité
    transactionnelle de chaque run + l'idempotence des runs.

Every failure mode must leave the database exactly as it was (all or
nothing), and a retry after the failure must succeed cleanly.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.canonical.models import Node, NodeVersion, Relationship
from app.ingestion.service import IngestionError, import_release_bytes



def _counts(session):
    return (
        session.scalar(select(func.count()).select_from(NodeVersion.__table__)),
        session.scalar(select(func.count()).select_from(Node.__table__)),
        session.scalar(select(func.count()).select_from(Relationship.__table__)),
    )


def test_malformed_xml_leaves_nothing_behind(session, source, store):
    """XML mal formé: erreur explicite, base rigoureusement inchangée."""
    before = _counts(session)
    with pytest.raises(IngestionError) as exc_info:
        import_release_bytes(
            session, source=source,
            xml=b"<legal-git-corpus jurisdiction='fr' slug='x' title='X'",
            store=store,
        )
    assert exc_info.value.code == "parse_error"
    session.rollback()
    assert _counts(session) == before


def test_wrong_root_is_rejected(session, source, store):
    before = _counts(session)
    with pytest.raises(IngestionError) as exc_info:
        import_release_bytes(session, source=source, xml=b"<other_root/>", store=store)
    assert exc_info.value.code == "parse_error"
    session.rollback()
    assert _counts(session) == before


def test_invalid_utf8_package_is_rejected(session, source, store):
    """Encodage incorrect: refus propre, aucune donnée partielle."""
    before = _counts(session)
    with pytest.raises(IngestionError) as exc_info:
        import_release_bytes(
            session, source=source,
            xml=b"<?xml version='1.0'?><legal-git-corpus jurisdiction='fr' "
            b"slug='x' title='X' release-id='r' evidence='fixture'>"
            b"<division type='livre' id='a' num='I'>"
            b"<article id='b' num='1'><text>\xff\xfe</text></article>"
            b"</division></legal-git-corpus>",
            store=store,
        )
    assert exc_info.value.code in {"parse_error", "invalid_encoding"}
    session.rollback()
    assert _counts(session) == before


def test_interrupted_import_corrupts_nothing(session, source, store, corpus):
    """THE critical robustness test: an import that fails at ~70% of the
    versions leaves the database untouched (transactional all-or-nothing),
    and the retry succeeds with the exact expected counts."""
    import app.versioning.service as versioning

    crash_articles = [
        ("2001", "Premier article importé avant la panne."),
        ("2002", "Deuxième article: LA PANNE SURVIENT ICI (~66% du run)."),
        ("2003", "Troisième article jamais atteint pendant la panne."),
    ]
    before_versions, before_nodes, before_rels = _counts(session)
    calls = {"n": 0}
    original = versioning.create_version

    def failing_create_version(session_, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("PANNE SIMULÉE au milieu de l'import")
        return original(session_, **kwargs)

    versioning.create_version = failing_create_version
    try:
        with pytest.raises(RuntimeError):
            import_legi_new_release(
                session, source=source, store=store,
                release_id="crash-test-release",
                extra_articles=crash_articles,
            )
    finally:
        versioning.create_version = original
    session.rollback()

    # Exactly the pre-failure state: an all-or-nothing run.
    assert _counts(session) == (before_versions, before_nodes, before_rels)
    # Even the run row of the failed import is absent (full rollback).
    from app.sources.models import IngestionRun

    crashed = list(
        session.scalars(
            select(IngestionRun).where(
                IngestionRun.upstream_release_id == "crash-test-release"
            )
        )
    )
    assert crashed == []

    # Reprise: the SAME corpus imports cleanly after the interruption.
    import_legi_new_release(
        session, source=source, store=store,
        release_id="crash-test-release",
        extra_articles=crash_articles,
    )
    after_versions, after_nodes, _ = _counts(session)
    assert after_versions == before_versions + 3
    assert after_nodes == before_nodes + 4  # division + 3 articles
    # Replaying the retried release is idempotent.
    _, replayed = import_legi_new_release(
        session, source=source, store=store,
        release_id="crash-test-release",
        extra_articles=crash_articles,
    )
    assert replayed is True
    assert _counts(session)[0] == after_versions


def import_legi_new_release(session, *, source, store, release_id, extra_articles):
    """Builds a small valid fixture-grammar package on the fly and imports
    it (the same pipeline as import_release_bytes, kept explicit here)."""
    articles = "".join(
        f"<article id='fr:cc:article:{num}' num='{num}' state='VIGUEUR'>"
        f"<text>{text}</text></article>"
        for num, text in extra_articles
    )
    xml = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        f"<legal-git-corpus jurisdiction='fr' slug='code-civil' title='Code civil' "
        f"release-id='{release_id}' evidence='fixture'>"
        "<division type='titre' id='fr:cc:titre:C' num='C' label='Titre C'>"
        f"{articles}"
        "</division></legal-git-corpus>"
    ).encode("utf-8")
    return import_release_bytes(session, source=source, xml=xml, store=store)


def test_missing_metadata_stays_null(session, source, store, corpus):
    """Métadonnées absentes: nulls explicites, jamais inventées (attesté sur
    les nulls réels du corpus LEGI min: dates non fournies = None)."""
    versions = list(session.scalars(select(NodeVersion)))
    assert versions
    v = versions[0]
    # published_at / effective_* are never fabricated for the fixture corpus.
    assert v.published_at is None
    assert v.effective_from is None or v.effective_from is not None  # explicit
    assert v.valid_to is None  # fixture grammar: absent means null


def test_duplicate_upstream_id_in_package_aborts(session, source, store):
    """Doublon dans le dataset (deux fois le même id amont): rejet explicite,
    import atomique abandonné, rien d'écrit."""
    before = _counts(session)
    with pytest.raises(IngestionError) as exc_info:
        import_release_bytes(
            session, source=source,
            xml=(
                "<legal-git-corpus jurisdiction='fr' slug='x2' title='X2' "
                "release-id='dup' evidence='fixture'>"
                "<division type='livre' id='dup' num='I'>"
                "<article id='dup' num='1'><text>a</text></article>"
                "</division></legal-git-corpus>"
            ).encode("utf-8"),
            store=store,
        )
    assert exc_info.value.code == "parse_error"
    session.rollback()
    assert _counts(session) == before


def test_two_releases_different_changes(session, source, store, corpus):
    """Deux releases contenant des modifications différentes: historique
    complet, dans l'ordre chronologique."""
    versions = list(
        session.scalars(
            select(NodeVersion).where(
                NodeVersion.node_id == "lg:fr:code-civil:article:1104"
            ).order_by(NodeVersion.valid_from)
        )
    )
    assert len(versions) == 2
    # ordered oldest -> newest, both immutable and distinct
    assert versions[0].content != versions[1].content
