"""Acceptance criteria C and D: version integrity, dates, text/fragments."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.canonical.models import NodeVersion
from app.canonical.service import DomainError
from app.core import sha256_hex
from app.versioning import service as versioning
from tests.conftest import NODE_1103, NODE_1104


def test_node_has_multiple_immutable_versions(session, corpus):
    versions = list(session.scalars(
        select(NodeVersion).where(NodeVersion.node_id == NODE_1104)
    ))
    assert len(versions) == 2
    hashes = {v.content_hash for v in versions}
    assert len(hashes) == 2
    texts = {v.content for v in versions}
    assert len(texts) == 2


def test_existing_version_cannot_be_overwritten(session, corpus):
    version = session.scalars(
        select(NodeVersion).where(NodeVersion.node_id == NODE_1104)
    ).first()
    with pytest.raises(DomainError) as exc_info:
        version.content = "texte modifié hors pipeline"
        session.flush()
    assert exc_info.value.code == "version_immutable"
    session.rollback()


def test_version_api_has_no_update_path(session, corpus):
    """No service function updates versions; the guard above closes the ORM
    layer. SQL-level updates are out of scope for V1 and documented in
    docs/limitations.md."""
    public_names = [name for name in dir(versioning) if not name.startswith("_")]
    updaters = [n for n in public_names if "update" in n]
    assert updaters == []


def test_content_hash_is_reproducible_and_prefixed(session, corpus):
    version = session.scalars(select(NodeVersion)).first()
    expected = f"sha256:{sha256_hex(version.content)}"
    assert version.content_hash == expected


def test_versions_traceable_to_source_and_ingestion_run(session, source, corpus):
    for version in session.scalars(select(NodeVersion)):
        assert version.source_id == source.id
        assert version.ingestion_run_id is not None
        assert version.ingested_at is not None
        run = corpus["run1"] if version.ingestion_run_id == corpus["run1"].id else corpus["run2"]
        assert run.id == version.ingestion_run_id


def test_legal_dates_kept_separate_and_may_be_null(session, corpus):
    import app.versioning.service as vs

    v1103 = session.scalars(
        select(NodeVersion).where(NodeVersion.node_id == NODE_1103)
    ).first()
    v1104 = session.scalars(
        select(NodeVersion).where(NodeVersion.node_id == NODE_1104)
    ).first()
    # valid_from preserved as a distinct concept; other date fields stay null
    # exactly because the fixture does not provide them (never invented).
    assert v1103.valid_from == date(2016, 10, 1)
    assert v1103.valid_to is None
    assert v1103.published_at is None
    assert v1103.effective_from is None
    assert v1103.effective_to is None
    assert v1104.valid_from is None

    invalid = [{"valid_from": date(2020, 1, 2), "valid_to": date(2020, 1, 1)}]
    for fields in invalid:
        with pytest.raises(DomainError) as exc_info:
            vs.validate_dates(
                fields["valid_from"], fields["valid_to"], None, None
            )
        assert exc_info.value.code == "invalid_dates"


def test_no_invented_history_for_stable_content(session, corpus):
    """Re-observing identical content in release 2 creates no version: the
    system does not invent historical versions."""
    v1103 = list(session.scalars(
        select(NodeVersion).where(NodeVersion.node_id == NODE_1103)
    ))
    v1105 = list(session.scalars(
        select(NodeVersion).where(NodeVersion.node_id == "lg:fr:code-civil:article:1105")
    ))
    assert len(v1103) == 1
    assert len(v1105) == 1


def test_text_preservation_is_byte_exact(session, corpus):
    """The fixture release-2 article 1104 has a two-alinea CDATA body; both
    the text and punctuation are preserved (after documented XML decoding)."""
    versions = session.scalars(
        select(NodeVersion).where(NodeVersion.node_id == NODE_1104)
    )
    new_version = max(versions, key=lambda v: len(v.content))
    expected = (
        "Les contrats doivent être négociés, formés et exécutés de bonne foi.\n"
        "Cette disposition est d'ordre public."
    )
    assert new_version.content == expected


def test_fragment_offsets_are_version_scoped(session, corpus):
    """The same [start, end) range is only valid against the exact version
    it was computed for; it is never silently reused across versions."""
    from app.core import CoreError, extract_fragment

    versions = list(
        session.scalars(select(NodeVersion).where(NodeVersion.node_id == NODE_1104))
    )
    old, new = sorted(versions, key=lambda v: len(v.content))
    old_len = len(old.content)
    new_len = len(new.content)
    assert old_len < new_len

    # Identical offsets in the shared prefix address identical text:
    old_tail = extract_fragment(
        old.content, old_len - 3, old_len, "unicode_code_point"
    )
    assert old_tail["text"] == "oi."
    same_in_new = extract_fragment(
        new.content, old_len - 3, old_len, "unicode_code_point"
    )
    assert same_in_new["text"] == "oi."

    # Offsets past the old length are valid only against the new version:
    continuation = extract_fragment(
        new.content, old_len, old_len + 7, "unicode_code_point"
    )
    assert continuation["text"] == "\nCette "
    with pytest.raises(CoreError) as exc_info:
        extract_fragment(
            old.content, old_len, old_len + 1, "unicode_code_point"
        )
    assert exc_info.value.code == "invalid_range"


def test_integrity_check_detects_corruption(session, corpus):
    version = session.scalars(select(NodeVersion)).first()
    versioning.verify_content_integrity(version)  # intact

    # Corruption simulated at the storage layer: stored content no longer
    # matches the recorded hash. (Not flushed: the immutability guard
    # would reject any update.)
    version.content = "corrompu"
    with pytest.raises(DomainError) as exc_info:
        versioning.verify_content_integrity(version)
    assert exc_info.value.code == "content_hash_mismatch"
