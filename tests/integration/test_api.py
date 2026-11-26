"""Acceptance criteria E and F: diff, fragments, API surface, pagination."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select

from app.canonical.models import NodeVersion
from tests.conftest import DOC_ID, NODE_1103, NODE_1104


def _versions_of(session, node_id):
    return list(
        session.scalars(select(NodeVersion).where(NodeVersion.node_id == node_id))
    )


def test_documents_list_with_filters_and_pagination(client, session, corpus):
    response = client.get("/v1/documents")
    assert response.status_code == 200
    body = response.json()
    assert body["has_more"] is False
    assert [d["id"] for d in body["items"]] == [DOC_ID]
    assert body["items"][0]["document_type"] == "code"
    assert body["items"][0]["metadata"]["evidence"] == "fixture"

    assert client.get("/v1/documents", params={"jurisdiction": "de"}).json()["items"] == []
    assert client.get(
        "/v1/documents", params={"q": "civil"}
    ).json()["items"][0]["id"] == DOC_ID

    bad = client.get("/v1/documents", params={"limit": 500})
    assert bad.status_code == 400
    assert bad.json()["code"] == "invalid_limit"

    page1 = client.get("/v1/documents", params={"limit": 1}).json()
    assert page1["has_more"] is False  # single document in fixture


def test_error_shape_is_consistent(client, corpus):
    response = client.get("/v1/documents/lg:fr:inconnu")
    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"code", "message"}
    assert body["code"] == "not_found"

    response = client.get("/v1/nodes/lg:fr:code-civil:article:9999")
    assert response.status_code == 200  # node exists (release 1)

    response = client.get("/v1/documents/lg%3Afr%3Ainconnu%3Axx/versions")
    assert response.status_code == 404


def test_document_tree(client, corpus):
    response = client.get(f"/v1/documents/{DOC_ID}/tree")
    assert response.status_code == 200
    tree = response.json()
    assert tree["document_id"] == DOC_ID
    (livre,) = tree["roots"]
    assert livre["node_type"] == "livre"
    (titre,) = livre["children"]
    assert [c["identifier"] for c in titre["children"]] == [
        "1101", "1103", "1104", "1105", "9999",
    ]


def test_node_detail_children_and_versions(client, session, corpus):
    response = client.get(f"/v1/nodes/{NODE_1103}")
    assert response.status_code == 200
    node = response.json()
    assert node["identifier"] == "1103"
    assert node["upstream_id"] == "fr:cc:article:1103"
    assert node["parent_id"] == "lg:fr:code-civil:titre:iii"
    assert node["document_id"] == DOC_ID

    children = client.get("/v1/nodes/lg:fr:code-civil:livre:iii/children").json()
    assert [c["id"] for c in children["items"]] == ["lg:fr:code-civil:titre:iii"]
    assert children["has_more"] is False

    versions = client.get(f"/v1/nodes/{NODE_1103}/versions").json()
    assert len(versions["items"]) == 1
    assert versions["items"][0]["valid_from"] == "2016-10-01"


def test_version_detail_has_provenance_and_hash_prefix(client, session, corpus):
    (version,) = _versions_of(session, NODE_1103)
    response = client.get(f"/v1/nodes/{NODE_1103}/versions/{version.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["content"].startswith("Les contrats")
    assert body["content_hash"].startswith("sha256:")
    assert body["content_hash"] == f"sha256:{hashlib.sha256(body['content'].encode()).hexdigest()}"
    assert body["representation_id"] == "plain-text-v1"
    assert body["provenance"]["ingestion_run_id"] == corpus["run1"].id
    assert body["provenance"]["upstream_release_id"] == "demo-release-2024-06"
    assert body["metadata"]["evidence"] == "fixture"


def test_diff_endpoint_punctuation_and_insert_detection(client, session, corpus):
    old, new = sorted(_versions_of(session, NODE_1104), key=lambda v: len(v.content))
    response = client.get(
        f"/v1/nodes/{NODE_1104}/diff",
        params={"from": old.id, "to": new.id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["node_id"] == NODE_1104
    assert body["from_version_id"] == old.id
    assert body["to_version_id"] == new.id
    assert body["algorithm"] == "character-range-diff-v1"
    assert body["is_legal_interpretation"] is False
    assert set(body["source_provenance"]) == {"from", "to"}

    # The second alinea insertion is a single insert at the end of the old
    # text, with exact code-point ranges.
    (change,) = body["changes"]
    assert change["operation"] == "insert"
    assert change["old_start"] == change["old_end"] == len(old.content)
    assert change["new_text"] == "\nCette disposition est d'ordre public."

    # Punctuation-only change detection:
    v1103 = _versions_of(session, NODE_1103)[0]
    punctuation = client.get(
        f"/v1/nodes/{NODE_1103}/diff", params={"from": v1103.id, "to": v1103.id}
    )
    assert punctuation.status_code == 200
    assert punctuation.json()["changes"] == []

    # Cross-node diff is rejected:
    v_other = _versions_of(session, "lg:fr:code-civil:article:1101")[0]
    mixed = client.get(
        f"/v1/nodes/{NODE_1103}/diff", params={"from": v1103.id, "to": v_other.id}
    )
    assert mixed.status_code == 400
    assert mixed.json()["code"] == "version_node_mismatch"


def test_fragment_endpoint_and_validation(client, session, corpus):
    version = _versions_of(session, NODE_1103)[0]
    content = version.content
    assert content[4:12] == "contrats"

    response = client.get(
        f"/v1/node-versions/{version.id}/fragment",
        params={"start": 4, "end": 12, "representation": "plain-text-v1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "contrats"
    assert body["offset_unit"] == "unicode_code_point"
    assert body["version_id"] == version.id
    assert body["content_length"] == len(content)

    out_of_range = client.get(
        f"/v1/node-versions/{version.id}/fragment",
        params={"start": 0, "end": 10_000, "representation": "plain-text-v1"},
    )
    assert out_of_range.status_code == 400
    assert out_of_range.json()["code"] == "invalid_range"

    inverted = client.get(
        f"/v1/node-versions/{version.id}/fragment",
        params={"start": 12, "end": 4, "representation": "plain-text-v1"},
    )
    assert inverted.status_code == 400
    assert inverted.json()["code"] == "invalid_range"

    bad_representation = client.get(
        f"/v1/node-versions/{version.id}/fragment",
        params={"start": 4, "end": 12, "representation": "html-v9"},
    )
    assert bad_representation.status_code == 400
    assert bad_representation.json()["code"] == "representation_mismatch"

    missing = client.get(
        "/v1/node-versions/lgv:fr:code-civil:article:1103:doesnotexist/fragment",
        params={"start": 0, "end": 1, "representation": "plain-text-v1"},
    )
    assert missing.status_code == 404


def test_sources_endpoints(client, corpus):
    body = client.get("/v1/sources").json()
    assert body["items"][0]["id"] == "fixture-code-civil"
    assert body["items"][0]["jurisdiction"] == "fr"
    source = client.get("/v1/sources/fixture-code-civil").json()
    assert source["name"].startswith("Code civil fixture")
    assert client.get("/v1/sources/unknown").status_code == 404


def test_document_snapshots_and_changes(client, session, corpus):
    body = client.get(f"/v1/documents/{DOC_ID}/versions").json()
    assert [s["upstream_release_id"] for s in body["items"]] == [
        "demo-release-2024-06",
        "demo-release-2025-01",
    ]
    run1, run2 = corpus["run1"].id, corpus["run2"].id

    response = client.get(
        f"/v1/documents/{DOC_ID}/changes", params={"from": run1, "to": run2}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["algorithm"] == "document-snapshot-diff-v1"
    operations = {c["operation"] for c in body["changes"]}
    assert operations == {"node_added", "node_changed", "node_removed"}
    added = [c for c in body["changes"] if c["operation"] == "node_added"]
    changed = [c for c in body["changes"] if c["operation"] == "node_changed"]
    removed = [c for c in body["changes"] if c["operation"] == "node_removed"]
    assert added[0]["node_id"] == "lg:fr:code-civil:article:1101"
    assert changed[0]["node_id"] == NODE_1104
    assert removed[0]["node_id"] == "lg:fr:code-civil:article:9999"
    # 1103 and 1105 are unchanged between snapshots: not listed.
    assert body["is_legal_interpretation"] is False


def test_export_ndjson_and_checksum(client, corpus):
    manifest = client.get("/v1/exports").json()
    assert manifest["items"][0]["corpus_id"] == DOC_ID
    assert manifest["items"][0]["records"]["nodes"] == 7

    response = client.get(f"/v1/exports/{DOC_ID}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    digest = hashlib.sha256(response.content).hexdigest()
    assert response.headers["x-legalgit-export-sha256"] == f"sha256:{digest}"

    lines = response.text.strip().splitlines()
    records = [json.loads(line) for line in lines]
    by_type = {}
    for record in records:
        by_type.setdefault(record["type"], []).append(record)
    assert by_type["manifest"][0]["records"]["node_versions"] == 6
    # No parser needed downstream: pure JSON records per line.
    assert by_type["document"][0]["id"] == DOC_ID
    version_contents = {r["content"] for r in by_type["node_version"]}
    assert any(
        c.endswith("Cette disposition est d'ordre public.")
        for c in version_contents
    )


def test_openapi_is_published(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert spec["info"]["title"].startswith("Legal Git")
    paths = spec["paths"]
    assert "/v1/documents" in paths
    assert "/v1/nodes/{node_id}/diff" in paths
    assert "/v1/node-versions/{version_id}/fragment" in paths
    assert "/v1/exports/{corpus_id}" in paths


def test_health_endpoints(client):
    assert client.get("/healthz").json()["status"] == "ok"
    ready = client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["database"] == "ok"


def test_metrics_endpoint(client, corpus):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    body = response.text
    # HTTP counter recorded the scrape-independent calls made so far.
    assert "legalgit_http_requests_total" in body
    # Gauges reflect the corpus state.
    assert "legalgit_node_versions" in body
    # Trigger at least one counted request after the first scrape:
    client.get("/v1/documents")
    body2 = client.get("/metrics").text
    assert "legalgit_ingestion_runs" in body2
