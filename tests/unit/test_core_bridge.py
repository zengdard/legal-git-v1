"""Cross-language bridge tests: the pybind11 core behaves like its tested
C++ counterpart from Python."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app import core
from app.core import CoreError

ARTICLE_1103 = "Les contrats légalement formés tiennent lieu de loi à ceux qui les ont faits."
RELEASE_1 = Path(__file__).resolve().parents[2] / "fixtures" / "code-civil" / "demo-release-2024-06.xml"


def test_sha256_matches_hashlib():
    assert core.sha256_hex(ARTICLE_1103) == hashlib.sha256(
        ARTICLE_1103.encode("utf-8")
    ).hexdigest()


def test_diff_punctuation_only_change():
    result = core.diff_text(ARTICLE_1103 + ".", ARTICLE_1103 + ",")
    assert result["algorithm"] == "character-range-diff-v1"
    assert result["offset_unit"] == "unicode_code_point"
    (change,) = result["changes"]
    assert change["operation"] == "replace"
    assert change["old_text"] == "."
    assert change["new_text"] == ","


def test_diff_code_point_offsets_with_accents():
    result = core.diff_text("contrat légal", "contrat legal")
    (change,) = result["changes"]
    assert change["old_start"] == 9
    assert change["old_end"] == 10
    assert change["old_text"] == "é"


def test_fragment_extracts_accents_as_single_code_points():
    fragment = core.extract_fragment("contrat légal", 9, 10, "unicode_code_point")
    assert fragment["text"] == "é"
    assert fragment["content_length"] == 13


def test_fragment_rejects_out_of_range():
    with pytest.raises(CoreError) as exc_info:
        core.extract_fragment("abc", 0, 4, "unicode_code_point")
    assert exc_info.value.code == "invalid_range"


def test_fragment_rejects_unknown_unit():
    with pytest.raises(CoreError) as exc_info:
        core.extract_fragment("abc", 0, 1, "utf8_byte")
    assert exc_info.value.code == "invalid_offset_unit"


def test_version_fingerprint_determinism_and_null_vs_value():
    base = core.fingerprint_of_version(
        content_format="plain_text",
        content="c",
        upstream_version_id="UP",
        valid_from=None,
        valid_to=None,
        published_at=None,
        effective_from=None,
        effective_to=None,
    )
    same = core.fingerprint_of_version(
        content_format="plain_text",
        content="c",
        upstream_version_id="UP",
        valid_from=None,
        valid_to=None,
        published_at=None,
        effective_from=None,
        effective_to=None,
    )
    other_date = core.fingerprint_of_version(
        content_format="plain_text",
        content="c",
        upstream_version_id="UP",
        valid_from="2016-10-01",
        valid_to=None,
        published_at=None,
        effective_from=None,
        effective_to=None,
    )
    assert base == same
    assert base != other_date


def test_parse_corpus_fixture_release_1():
    parsed = core.parse_corpus_xml(RELEASE_1.read_text("utf-8"))
    assert parsed["corpus"]["release_id"] == "demo-release-2024-06"
    assert parsed["corpus"]["evidence"] == "fixture"
    assert len(parsed["nodes"]) == 6
    article_1103 = next(
        n for n in parsed["nodes"] if n["upstream_id"] == "fr:cc:article:1103"
    )
    assert article_1103["upstream_parent_id"] == "fr:cc:titre:III"
    versions_1103 = [
        v for v in parsed["versions"] if v["node_upstream_id"] == "fr:cc:article:1103"
    ]
    assert versions_1103[0]["content"] == ARTICLE_1103
    assert versions_1103[0]["valid_from"] == "2016-10-01"
    assert parsed["relationships"][0]["relationship_type"] == "related_to"
    assert parsed["relationships"][0]["upstream_type"] == "CONTEXTE"
    demo_article = next(
        n for n in parsed["nodes"] if n["upstream_id"] == "fr:cc:article:9999"
    )
    assert demo_article["metadata"].get("demo_only") is True
