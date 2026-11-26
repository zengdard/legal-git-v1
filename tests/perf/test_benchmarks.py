"""Performance and robustness benchmarks (category 8).

Run explicitly: pytest -m benchmark -s
Soft thresholds only (generous ceilings); the printed numbers feed the
performance baseline in docs/operations.md (mesurer d'abord, optimiser
ensuite — jamais l'inverse).
"""

from __future__ import annotations

import time

import pytest

pytestmark = pytest.mark.benchmark

SPEED_FLOOR = 0.25  # × the generous ceiling; anything slower fails


def _timed(fn, repeat=1):
    start = time.perf_counter()
    for _ in range(repeat):
        result = fn()
    elapsed = time.perf_counter() - start
    return result, elapsed / repeat


def test_hash_throughput_mb_per_second(benchmark_stats):
    """SHA-256 (core C++) — référence ~1 Go/s sur CPU moderne utile."""
    from app.core import sha256_hex

    payload = ("Les contrats légalement formés tiennent lieu de loi. " * 16_000).encode(
        "utf-8"
    )
    megabytes = len(payload) / 1_048_576
    _, elapsed = _timed(lambda: sha256_hex(payload))
    throughput = megabytes / elapsed
    benchmark_stats["hashing_mb_per_second"] = round(throughput, 1)
    print(f"\n[hash] {throughput:.0f} Mo/s ({megabytes:.1f} Mo en {elapsed*1000:.1f} ms)")
    assert throughput > 100 * SPEED_FLOOR


def test_diff_real_articles_per_comparison(benchmark_stats):
    """Diff d'articles réels (paires LEGI, ~1 Ko chacune)."""
    from app.core import diff_text

    old = ("Article numero %d du dispositif legal. " % 7) * 40
    new = ("Article numero %d du dispositif general. " % 7) * 40
    _, elapsed = _timed(lambda: diff_text(old, new), repeat=20)
    per_diff_ms = elapsed * 1000
    benchmark_stats["diff_ms_per_article_pair"] = round(per_diff_ms, 3)
    print(f"\n[diff] {per_diff_ms:.2f} ms par comparaison d'article (~{len(old)} cps)")
    assert per_diff_ms < 50


def test_fragment_extraction_throughput(benchmark_stats):
    from app.core import extract_fragment

    content = ("fragment mesuré sur une longue chaîne constituée d'accents éàü. " * 5000)
    _, elapsed = _timed(
        lambda: extract_fragment(content, 100, 500, "unicode_code_point"), repeat=200
    )
    per_call_us = elapsed * 1_000_000
    benchmark_stats["fragment_us_per_call"] = round(per_call_us, 1)
    print(f"\n[fragment] {per_call_us:.1f} µs par extraction")
    assert per_call_us < 2_000


def test_corpus_parse_throughput(benchmark_stats):
    """Parsing XML: fiches/secondes sur de vraies fiches DILA."""
    from pathlib import Path

    from app.core import parse_legi_article

    fiches = sorted(
        (
            Path(__file__).resolve().parents[2]
            / "tests"
            / "fixtures"
            / "legi-code-civil-mini"
            / "LEGITEXT000006070721"
            / "article"
        ).glob("*.xml")
    )
    payloads = [p.read_text("utf-8") for p in fiches]

    _, elapsed = _timed(lambda: [parse_legi_article(x) for x in payloads], repeat=50)
    per_fiche_us = elapsed * 1_000_000 / len(payloads)
    benchmark_stats["parse_us_per_fiche"] = round(per_fiche_us, 1)
    print(f"\n[parse] {per_fiche_us:.1f} µs par fiche ({len(payloads)} fiches)")
    assert per_fiche_us < 20_000


def test_tree_and_export_latency_on_synthesized_corpus(
    session, store, client, benchmark_stats
):
    """Volume moyenne gamme: 1 000 nodes -> latence arbre + débit export."""
    from sqlalchemy import select

    from app.canonical import service as canonical
    from app.canonical.models import Node, Document
    from app.sources.service import get_or_create_source

    source_id = "benchmark-source"

    get_or_create_source(
        session,
        source_id=source_id,
        name="benchmark",
        publisher=None,
        jurisdiction="fr",
        source_type="official_dataset",
    )
    existing = session.scalars(select(Document).where(
        Document.id == "lg:fr:code-benchmark"
    )).first()
    if existing:
        return  # corpus déjà en place (benchmarks rejouables)
    document, _ = canonical.get_or_create_document(
        session, source_id=source_id, jurisdiction="fr",
        slug="code-benchmark", title="Code benchmark", document_type="code",
    )
    canonical.get_or_create_node(
        session, document_id=document.id, node_type="titre",
        identifier="I", parent_id=None, label="Titre I", sort_order=0,
    )
    session.flush()
    parent = session.scalars(
        select(Node).where(Node.document_id == document.id, Node.node_type == "titre")
    ).first()
    text = "Un alinéa de texte raisonnable pour les mesures de sérialisation. "
    from app.versioning import service as versioning
    from app.sources.models import IngestionRun

    run = IngestionRun(
        id="run:benchmark", source_id=source_id, upstream_release_id="bench",
        status="completed", report={},
    )
    session.add(run)
    session.flush()
    for i in range(1000):
        node, created = canonical.get_or_create_node(
            session, document_id=document.id, node_type="article",
            identifier=str(1000 + i), parent_id=parent.id,
            label=f"Article {1000+i}", sort_order=i,
        )
        if created:
            versioning.create_version(
                session, node=node, source_id=source_id,
                ingestion_run_id=run.id, content=text + str(i),
            )
    session.commit()

    _, tree_ms = _timed(lambda: client.get(f"/v1/documents/{document.id}/tree"))
    benchmark_stats["tree_ms_1000_nodes"] = round(tree_ms * 1000, 1)
    print(f"\n[tree] {tree_ms*1000:.0f} ms pour 1 001 nodes")
    assert tree_ms < 5

    response, export_s = _timed(
        lambda: client.get(f"/v1/exports/{document.id}")
    )
    size_mb = len(response.content) / 1_048_576
    benchmark_stats["export_mb"] = round(size_mb, 2)
    benchmark_stats["export_seconds"] = round(export_s, 3)
    print(f"\n[export] {size_mb:.2f} Mo en {export_s:.2f} s "
          f"({size_mb/max(export_s, 1e-9):.1f} Mo/s)")
    assert response.status_code == 200
    assert export_s < 10
