"""PostgreSQL integration tests (category 7: Docker + PostgreSQL).

Activated when LEGALGIT_PG_URL is set (e.g. in CI with a real PostgreSQL
service, or locally with the compose database). Verifies what SQLite
cannot: JSONB semantics, the immutability TRIGGER in PL/pgSQL, constraints,
and a full real-corpus import inside a real transactional database.
"""

from __future__ import annotations

import os

import pytest

PG_URL = os.environ.get("LEGALGIT_PG_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="LEGALGIT_PG_URL not set: run with a real PostgreSQL to activate "
    "(CI provides one; locally: the compose db)",
)


@pytest.fixture(scope="module")
def pg_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.base import Base
    from app.db.triggers import apply_immutable_triggers

    engine = create_engine(PG_URL, future=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    apply_immutable_triggers(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    yield session
    session.rollback()
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_pg_immutable_trigger_blocks_mutation(pg_session):
    """The PL/pgSQL trigger (migration 0002) rejects UPDATE and DELETE on
    node_versions at the database level."""
    from sqlalchemy import text

    from app.ingestion.legi_adapter import LEGI_SOURCE
    from app.ingestion.legi_service import import_legi_release
    from app.sources.service import get_or_create_source
    from app.storage import LocalFilesystemStore

    import tempfile
    from pathlib import Path

    source, _ = get_or_create_source(pg_session, **LEGI_SOURCE)
    with tempfile.TemporaryDirectory() as tmp:
        run, replayed = import_legi_release(
            pg_session,
            source=source,
            texte_cid="LEGITEXT000006070721",
            base_dir=Path(__file__).resolve().parents[2]
            / "tests"
            / "fixtures"
            / "legi-code-civil-mini",
            release_label="Freemium_legi_global_20261108-140000.tar.gz",
            store=LocalFilesystemStore(root=Path(tmp)),
        )
    pg_session.commit()
    assert not replayed

    with pytest.raises(Exception, match="(?i)immutable"):
        pg_session.execute(
            text("UPDATE node_versions SET content = 'corrompu'")
        )
    pg_session.rollback()
    with pytest.raises(Exception, match="(?i)immutable"):
        pg_session.execute(text("DELETE FROM node_versions"))
    pg_session.rollback()


def test_pg_jsonb_and_real_history_roundtrip(pg_session):
    """JSONB metadata + the real versions survived the blind-mutation
    attempt above (transaction rolled back)."""
    from sqlalchemy import text

    count = pg_session.execute(
        text("SELECT count(*) FROM node_versions")
    ).scalar()
    assert count == 4  # article 1 (x2) + article 1103 (x2), real fiches

    jsonb = pg_session.execute(
        text("SELECT metadata->>'etat' FROM node_versions LIMIT 1")
    ).scalar()
    assert jsonb in {"VIGUEUR", "MODIFIE"}

    trigger = pg_session.execute(
        text(
            "SELECT tgname FROM pg_trigger "
            "WHERE tgrelid = 'node_versions'::regclass AND NOT tgisinternal"
        )
    ).scalar()
    assert trigger == "trg_node_versions_immutable"
