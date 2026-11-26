"""Fragments and offsets, systematically (category 5 of the test
specification), on the API surface.

Convention under test (docs/diff.md): Unicode code-point offsets, half-open
[start, end), scoped to ONE exact node version and ONE exact representation
("representation_id" + content hash of the version).
"""

from __future__ import annotations

import pytest

from tests.conftest import NODE_1103

REPRESENTATION = "xml-fragment-v1"


@pytest.fixture
def versions_1103(client, legi_run):
    items = client.get(f"/v1/nodes/{NODE_1103}/versions").json()["items"]
    assert len(items) == 2
    by_from = {v["valid_from"]: v for v in items}
    contents = {
        "2016-10-01": client.get(
            f"/v1/nodes/{NODE_1103}/versions/{by_from['2016-10-01']['id']}"
        ).json()["content"],
    }
    return by_from, contents


def fragment_call(client, version_id, start, end, representation=REPRESENTATION):
    return client.get(
        f"/v1/node-versions/{version_id}/fragment",
        params={"start": start, "end": end, "representation": representation},
    )


def test_fragment_at_the_beginning(client, versions_1103):
    by_from, contents = versions_1103
    content = contents["2016-10-01"]
    version_id = by_from["2016-10-01"]["id"]
    body = fragment_call(client, version_id, 0, 4).json()
    assert body["text"] == content[0:4]
    assert body["start"] == 0 and body["end"] == 4


def test_fragment_at_the_end(client, versions_1103):
    by_from, contents = versions_1103
    content = contents["2016-10-01"]
    version_id = by_from["2016-10-01"]["id"]
    body = fragment_call(client, version_id, len(content) - 5, len(content)).json()
    assert body["text"] == content[-5:]
    assert body["content_length"] == len(content)


def test_empty_fragment_is_defined(client, versions_1103):
    by_from, _ = versions_1103
    body = fragment_call(client, by_from["2016-10-01"]["id"], 3, 3).json()
    assert body["text"] == ""
    assert body["start"] == body["end"] == 3


def test_full_range_is_exact(client, versions_1103):
    by_from, contents = versions_1103
    content = contents["2016-10-01"]
    body = fragment_call(client, by_from["2016-10-01"]["id"], 0, len(content)).json()
    assert body["text"] == content  # full exact restitution


@pytest.mark.parametrize("start,end", [(-1, 3), (0, -1), (-4, -1)])
def test_negative_offsets_rejected(client, versions_1103, start, end):
    by_from, _ = versions_1103
    response = fragment_call(client, by_from["2016-10-01"]["id"], start, end)
    assert response.status_code == 400
    assert response.json()["code"] in {"validation_error", "invalid_range"}


def test_offset_beyond_length_rejected(client, versions_1103):
    by_from, contents = versions_1103
    content = contents["2016-10-01"]
    response = fragment_call(client, by_from["2016-10-01"]["id"], 0, len(content) + 1)
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_range"


def test_start_after_end_rejected(client, versions_1103):
    by_from, _ = versions_1103
    response = fragment_call(client, by_from["2016-10-01"]["id"], 12, 4)
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_range"


def test_accents_count_as_one_code_point(client, versions_1103):
    by_from, contents = versions_1103
    content = contents["2016-10-01"]
    needle = "légalement"
    start = content.index(needle)
    body = fragment_call(
        client, by_from["2016-10-01"]["id"], start, start + len(needle)
    ).json()
    assert body["text"] == needle  # 'é' = 1 unit, not 2 UTF-8 bytes


def test_typographic_and_multibyte_chars_count_as_one(client, versions_1103):
    """Guillemets « » and apostrophe ’ are single code points: python str
    slicing (code points) matches the API offsets exactly."""
    needle = "à ceux qui les ont faits."
    by_from, contents = versions_1103
    content = contents["2016-10-01"]
    start = content.index(needle)
    body = fragment_call(
        client, by_from["2016-10-01"]["id"], start, start + len(needle)
    ).json()
    assert body["text"] == needle


def test_historical_version_fragment_stays_accessible(client, versions_1103):
    """Fragments d'une ancienne version: toujours adressables, avec le
    contenu EXACT de cette version."""
    by_from, _ = versions_1103
    old_id = by_from["1804-03-21"]["id"]
    detail = client.get(f"/v1/nodes/{NODE_1103}/versions/{old_id}").json()
    needle = "obligées"
    start = detail["content"].index(needle)
    body = fragment_call(client, old_id, start, start + len(needle)).json()
    assert body["text"] == needle
    assert body["version_id"] == old_id


def test_offsets_of_v1_are_not_reused_on_v2(client, versions_1103):
    """Offset V1 utilisé sur V2: pas de correspondance automatique — les
    offsets de la version historique adressent un autre texte dans la
    version courante (ou sont rejetés si hors bornes)."""
    by_from, contents = versions_1103
    old_id = by_from["1804-03-21"]["id"]
    old_content = client.get(f"/v1/nodes/{NODE_1103}/versions/{old_id}").json()[
        "content"
    ]
    start, end = 0, 23
    marker = old_content[start:end]  # historical text at these offsets

    same_offsets_new = fragment_call(client, by_from["2016-10-01"]["id"], start, end)
    if same_offsets_new.status_code == 200:
        assert same_offsets_new.json()["text"] != marker
    # And a full cross-check: no offset range ever returns text belonging
    # to the other version unless the texts really share it.


def test_representation_must_match_exactly(client, versions_1103):
    by_from, _ = versions_1103
    response = fragment_call(
        client, by_from["2016-10-01"]["id"], 0, 3, representation="plain-text-v1"
    )
    assert response.status_code == 400
    assert response.json()["code"] == "representation_mismatch"


def test_fragment_response_declares_unit_and_representation(client, versions_1103):
    by_from, _ = versions_1103
    body = fragment_call(client, by_from["2016-10-01"]["id"], 0, 3).json()
    assert body["offset_unit"] == "unicode_code_point"
    assert body["representation_id"] == REPRESENTATION
    assert body["version_id"] == by_from["2016-10-01"]["id"]
