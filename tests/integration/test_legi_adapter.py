"""LEGI adapter: integration tests against a mini corpus of REAL DILA
fiches (tests/fixtures/legi-code-civil-mini, licence ouverte v2.0).

Covers acceptance criteria A (provenance, idempotency), B (hierarchy),
C (real version history), E/F (diff and API behaviour) against the real
source format.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.canonical.models import Node, NodeVersion, Relationship
from app.ingestion.legi_adapter import LEGI_SOURCE
from app.ingestion.legi_service import import_legi_release
from app.sources.service import get_or_create_source
from app.storage import LocalFilesystemStore
from tests.conftest import DOC_ID

MINI_DIR = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "legi-code-civil-mini"
)
NODE_1103 = "lg:fr:code-civil:article:1103"
TEXTe_CID = "LEGITEXT000006070721"  # noqa: N816 - kept for clarity


def test_provenance_and_attribution(session, legi_run):
    """The run identifies the real source, its licence and the attribution
    mention required by licence ouverte v2.0."""
    assert legi_run.source_id == "legi"
    assert legi_run.upstream_release_id.endswith(TEXTe_CID)
    assert legi_run.report["licence"] == "Licence ouverte v2.0"
    assert "DILA" in legi_run.report["attribution"]
    assert "legifrance.gouv.fr" in legi_run.report["authority_note"]
    assert legi_run.raw_artifact_uri.startswith("storage://raw/")
    assert legi_run.report["raw_artifact_bytes"] > 0


def test_import_counts(session, legi_run):
    counts = legi_run.report["counts"]
    # 7 real section fiches -> 5 logical sections: the Titre III and the
    # Chapitre Ier fiches share their cid across the 2016 rename.
    assert counts["sections_created"] == 5
    assert counts["sections_unchanged"] == 2
    assert counts["articles_created"] == 2  # article 1 + article 1103
    assert counts["versions_created"] == 4  # 2 versions per article


def test_article_1103_has_real_version_history(session, legi_run):
    """Two immutable versions with the REAL dates of validity of the source
    (the historical system does not invent anything)."""
    versions = list(
        session.scalars(
            select(NodeVersion).where(NodeVersion.node_id == NODE_1103)
        )
    )
    assert len(versions) == 2
    by_valid = {v.valid_from.isoformat(): v for v in versions}
    old = by_valid["1804-03-21"]
    new = by_valid["2016-10-01"]
    assert old.valid_to.isoformat() == "2016-10-01"
    assert new.valid_to.isoformat() == "2999-01-01"
    assert old.upstream_version_id == "LEGIARTI000006436088"
    assert new.upstream_version_id == "LEGIARTI000032040777"
    assert old.representation_id == "xml-fragment-v1"
    assert old.content_format == "xml_fragment"
    # The historical fiche carries markup; the current one is plain text.
    assert old.meta["contenu_has_markup"] is True
    assert new.meta["contenu_has_markup"] is False
    # Byte-for-byte preservation (trailing space included).
    assert new.content.endswith("à ceux qui les ont faits. ")


def test_continuity_despite_section_rename(session, legi_run):
    """Both 1103 fiches (old chapter 'Dispositions préliminaires', new
    chapter 'Dispositions liminaires') map onto ONE logical article: the
    continuity evidence is the shared VERSIONS list of the source."""
    nodes = list(
        session.scalars(select(Node).where(Node.identifier == "1103"))
    )
    assert len(nodes) == 1
    node = nodes[0]
    # The chapter renamed in 2016 ("Dispositions préliminaires" ->
    # "Dispositions liminaires") kept its LEGI cid: same logical parent.
    assert node.parent_id == "lg:fr:code-civil:section:legiscta000006136340"
    parent = session.get(Node, node.parent_id)
    assert parent.label == "Chapitre Ier : Dispositions liminaires"
    # The OLD version keeps its historical placement in metadata.
    old = session.scalars(
        select(NodeVersion)
        .where(NodeVersion.node_id == node.id)
        .order_by(NodeVersion.valid_from)
    ).first()
    assert old.meta["tm_chain"][-1]["id"] == "LEGISCTA000006136340"


def test_idempotent_replay(session, tmp_path):
    source, _ = get_or_create_source(session, **LEGI_SOURCE)
    store = LocalFilesystemStore(root=tmp_path)
    run1, replayed1 = import_legi_release(
        session,
        source=source,
        texte_cid=TEXTe_CID,
        base_dir=MINI_DIR,
        release_label="mini",
        store=store,
    )
    session.commit()
    run2, replayed2 = import_legi_release(
        session,
        source=source,
        texte_cid=TEXTe_CID,
        base_dir=MINI_DIR,
        release_label="mini",
        store=store,
    )
    session.commit()
    assert replayed1 is False
    assert replayed2 is True
    assert run2.id == run1.id
    versions = list(session.scalars(select(NodeVersion)))
    assert len(versions) == 4


def test_api_versions_and_diff(client, session, legi_run):
    response = client.get(f"/v1/nodes/{NODE_1103}/versions")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2

    old = next(v for v in items if v["valid_from"] == "1804-03-21")
    new = next(v for v in items if v["valid_from"] == "2016-10-01")

    # Provenance of a version points at the official source.
    detail = client.get(f"/v1/nodes/{NODE_1103}/versions/{new['id']}").json()
    assert detail["provenance"]["upstream_version_id"] == "LEGIARTI000032040777"
    assert detail["representation_id"] == "xml-fragment-v1"

    diff = client.get(
        f"/v1/nodes/{NODE_1103}/diff", params={"from": old["id"], "to": new["id"]}
    ).json()
    assert diff["algorithm"] == "character-range-diff-v1"
    assert diff["representation_id"] == "xml-fragment-v1"
    assert diff["is_legal_interpretation"] is False
    assert diff["changes"]

    # Cross-representation fragment addressing is rejected.
    assert (
        client.get(
            f"/v1/node-versions/{new['id']}/fragment",
            params={"start": 0, "end": 3, "representation": "plain-text-v1"},
        ).status_code
        == 400
    )


def test_tree_shows_real_structure(client, session, legi_run):
    tree = client.get(f"/v1/documents/{DOC_ID}/tree").json()
    labels = [root["label"] for root in tree["roots"]]
    assert any("Titre préliminaire" in label for label in labels)
    livre_iii = next(root for root in tree["roots"] if "Livre III" in root["label"])

    seen: list[tuple[str, str | None]] = []

    def walk(node: dict) -> None:
        for child in node["children"]:
            seen.append((child["node_type"], child.get("identifier")))
            walk(child)

    walk(livre_iii)
    assert ("article", "1103") in seen


def test_relationships_declare_their_upstream_evidence(session, legi_run):
    """Created relationships keep the LEGI typelien/sens, sens=cible links
    are counted (never inferred)."""
    counts = legi_run.report["counts"]
    assert counts["relationships_created"] >= 1
    assert "liens_sens_cible_skipped" in counts
    rel = session.scalars(select(Relationship)).first()
    assert rel.source_id == "legi"
    assert rel.meta.get("upstream_typelien") is not None
    assert rel.meta.get("upstream_sens") == "source"
