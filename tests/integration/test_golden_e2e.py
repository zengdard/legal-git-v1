"""THE golden end-to-end test (per the test specification):

    Prendre un article réel de Légifrance, importer deux versions
    historiques, vérifier leur contenu exact, calculer leur diff, retrouver
    un fragment précis dans chaque version, puis reconstruire l'historique
    complet à partir de l'API.

Runs on REAL DILA fiches (article 1103: the historical 1804-03-21 → 2016-10-01
version and the current one). If this scenario passes, the fundamental
promise of Legal Git is validated: the right text, in the right version, at
the right place, with verifiable provenance and exact history.
"""

from __future__ import annotations

import hashlib
import json


from tests.conftest import DOC_ID, NODE_1103

CURRENT_VALID_FROM = "2016-10-01"
HISTORICAL_VALID_FROM = "1804-03-21"
CURRENT_CONTENT = (
    "Les contrats légalement formés tiennent lieu de loi à ceux qui les ont "
    "faits. "
)


def _versions(client):
    return client.get(f"/v1/nodes/{NODE_1103}/versions").json()["items"]


def _versions_by_from(client):
    return {v["valid_from"]: v for v in _versions(client)}


def _detail(client, version_id):
    return client.get(f"/v1/nodes/{NODE_1103}/versions/{version_id}").json()


def test_1_article_has_two_real_historical_versions(client, legi_run):
    versions = _versions(client)
    assert len(versions) == 2
    by_from = _versions_by_from(client)
    assert set(by_from) == {HISTORICAL_VALID_FROM, CURRENT_VALID_FROM}
    # Real dates of validity of the Code civil article 1103.
    assert by_from[HISTORICAL_VALID_FROM]["valid_to"] == CURRENT_VALID_FROM
    assert by_from[CURRENT_VALID_FROM]["valid_to"] == "2999-01-01"
    # Chronological order: the versions list is retrievable in history order.
    froms = [v["valid_from"] for v in versions]
    assert froms == sorted(froms)


def test_2_exact_content_and_provenance_of_both_versions(client, legi_run):
    versions = _versions_by_from(client)

    # --- historical version (1804): real text, markup preserved
    old = _detail(client, versions[HISTORICAL_VALID_FROM]["id"])
    assert old["content"].startswith("<br/>")
    assert (
        "Il est unilatéral lorsqu'une ou plusieurs personnes sont obligées"
        in old["content"]
    )
    assert old["upstream_version_id"] == "LEGIARTI000006436088"
    provenance = old["provenance"]
    assert provenance["upstream_release_id"].endswith("LEGITEXT000006070721")
    assert provenance["ingestion_run_id"] == legi_run.id
    assert provenance["raw_artifact_uri"].startswith("storage://raw/")

    # --- current version (2016): exact text byte for byte, hash coherent
    new = _detail(client, versions[CURRENT_VALID_FROM]["id"])
    assert new["content"] == CURRENT_CONTENT  # trailing space included
    assert new["content_hash"] == "sha256:" + hashlib.sha256(
        new["content"].encode("utf-8")
    ).hexdigest()
    assert new["upstream_version_id"] == "LEGIARTI000032040777"
    assert new["representation_id"] == "xml-fragment-v1"


def test_3_diff_between_the_two_real_versions(client, legi_run):
    versions = _versions_by_from(client)
    response = client.get(
        f"/v1/nodes/{NODE_1103}/diff",
        params={
            "from": versions[HISTORICAL_VALID_FROM]["id"],
            "to": versions[CURRENT_VALID_FROM]["id"],
        },
    )
    assert response.status_code == 200
    diff = response.json()
    assert diff["node_id"] == NODE_1103
    assert diff["algorithm"] == "character-range-diff-v1"
    assert diff["is_legal_interpretation"] is False
    assert diff["changes"], "the real 1804 -> 2016 rewrite must be detected"

    # The real rewrite of a Code civil article is a large change; the old
    # and new sides of the blocks are genuine changed fragments (equal
    # regions are NOT part of the block texts — see docs/diff.md).
    with_old = [c for c in diff["changes"] if c["old_text"]]
    with_new = [c for c in diff["changes"] if c["new_text"]]
    assert with_old and with_new
    assert len(diff["changes"]) > 5

    # The blocks' ranges address their own side exactly: slicing the
    # historical version at [old_start, old_end) returns old_text.
    first = with_old[0]
    fragment = client.get(
        f"/v1/node-versions/{versions[HISTORICAL_VALID_FROM]['id']}/fragment",
        params={
            "start": first["old_start"],
            "end": first["old_end"],
            "representation": "xml-fragment-v1",
        },
    ).json()
    assert fragment["text"] == first["old_text"]


def test_4_precision_fragments_in_each_version(client, legi_run):
    versions = _versions_by_from(client)
    historical = _detail(client, versions[HISTORICAL_VALID_FROM]["id"])
    current = _detail(client, versions[CURRENT_VALID_FROM]["id"])

    # Locate a precise fragment in the CURRENT version.
    needle = "tiennent lieu de loi"
    start = current["content"].index(needle)
    end = start + len(needle)
    fragment_now = client.get(
        f"/v1/node-versions/{versions[CURRENT_VALID_FROM]['id']}/fragment",
        params={"start": start, "end": end, "representation": "xml-fragment-v1"},
    ).json()
    assert fragment_now["text"] == needle
    assert fragment_now["content_length"] == len(current["content"])

    # The very same offsets in the HISTORICAL version never address the
    # same text silently — offsets are version-scoped.
    same_offsets = client.get(
        f"/v1/node-versions/{versions[HISTORICAL_VALID_FROM]['id']}/fragment",
        params={"start": start, "end": end, "representation": "xml-fragment-v1"},
    )
    if same_offsets.status_code == 200:  # in range for the 1804 text
        assert same_offsets.json()["text"] != needle

    # A precise fragment of the HISTORICAL version remains accessible.
    needle_old = "unilatéral"
    start_old = historical["content"].index(needle_old)
    end_old = start_old + len(needle_old)
    fragment_then = client.get(
        f"/v1/node-versions/{versions[HISTORICAL_VALID_FROM]['id']}/fragment",
        params={
            "start": start_old,
            "end": end_old,
            "representation": "xml-fragment-v1",
        },
    ).json()
    assert fragment_then["text"] == needle_old


def test_5_hierarchy_places_the_article_correctly(client, legi_run):
    node = client.get(f"/v1/nodes/{NODE_1103}").json()
    assert node["parent_id"] == "lg:fr:code-civil:section:legiscta000006136340"
    parent = client.get(f"/v1/nodes/{node['parent_id']}").json()
    assert parent["label"] == "Chapitre Ier : Dispositions liminaires"

    tree = client.get(f"/v1/documents/{DOC_ID}/tree").json()

    labels: list[str] = []

    def walk(node_dict):
        labels.append(node_dict["label"] or "")
        for child in node_dict["children"]:
            walk(child)

    for root in tree["roots"]:
        walk(root)
    joined = " > ".join(labels)
    assert "Livre III" in joined
    assert "Des sources d'obligations" in joined
    assert "Chapitre Ier : Dispositions liminaires" in joined


def test_6_history_rebuilt_from_the_export(client, legi_run):
    """The full history is reconstructible from the machine-readable export
    alone: exact contents, real dates, stable ids, traceable provenance."""
    response = client.get(f"/v1/exports/{DOC_ID}")
    assert response.status_code == 200
    digest = hashlib.sha256(response.content).hexdigest()
    assert response.headers["x-legalgit-export-sha256"] == f"sha256:{digest}"

    records = [json.loads(line) for line in response.text.splitlines()]
    versions_1103 = [
        r for r in records
        if r["type"] == "node_version" and r["node_id"] == NODE_1103
    ]
    assert len(versions_1103) == 2
    by_from = {v["valid_from"]: v for v in versions_1103}
    assert set(by_from) == {HISTORICAL_VALID_FROM, CURRENT_VALID_FROM}
    assert by_from[CURRENT_VALID_FROM]["content"] == CURRENT_CONTENT
    assert by_from[CURRENT_VALID_FROM]["upstream_version_id"] == "LEGIARTI000032040777"
    assert (
        by_from[HISTORICAL_VALID_FROM]["upstream_version_id"]
        == "LEGIARTI000006436088"
    )
    # Export ids are exactly the ids served by the API (stability across
    # access paths).
    api_ids = {v["id"] for v in _versions(client)}
    for record in versions_1103:
        assert record["id"] in api_ids
