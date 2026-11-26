"""Test bootstrap.

Runs against a throwaway SQLite database under var/ and a per-test temporary
storage directory. The environment must be configured before importing any
`app` module (settings are instantiated at import time).
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

os.environ.setdefault("LEGALGIT_DATABASE_URL", f"sqlite:///{REPO_ROOT / 'var' / 'test.db'}")
os.environ.setdefault(
    "LEGALGIT_STORAGE_DIR", str(REPO_ROOT / "var" / "test-storage")
)
# V2 reviewer/admin keys for API tests (pilot-level static keys).

# SQLite does not create missing parent directories.
(REPO_ROOT / "var").mkdir(exist_ok=True)

import pytest
from fastapi.testclient import TestClient

# V2 models register their tables on Base.metadata; importing them here
# guarantees create_all covers them even when running a single test file
# that never imports the V2 modules itself.

from app.canonical.models import (  # noqa: E402
    Base,
)
from app.db.session import get_engine, get_session_factory
from app.db.triggers import apply_immutable_triggers
from app.ingestion.service import import_release_bytes
from app.sources.service import get_or_create_source
from app.storage import LocalFilesystemStore

FIXTURES = REPO_ROOT / "fixtures" / "code-civil"
RELEASE_1 = FIXTURES / "demo-release-2024-06.xml"
RELEASE_2 = FIXTURES / "demo-release-2025-01.xml"

SOURCE = dict(
    source_id="fixture-code-civil",
    name="Code civil fixture corpus (Legal Git demo)",
    publisher="Legal Git development fixture",
    jurisdiction="fr",
    source_type="official_dataset",
    base_uri=None,
    licence_name=None,
    licence_uri=None,
)

DOC_ID = "lg:fr:code-civil"
NODE_1103 = "lg:fr:code-civil:article:1103"
NODE_1104 = "lg:fr:code-civil:article:1104"
NODE_1105 = "lg:fr:code-civil:article:1105"


@pytest.fixture
def session():
    engine = get_engine()
    # Pooled connections may still carry PRAGMA foreign_keys=ON from a
    # previous test (set by apply_immutable_triggers); drops must run
    # with FK enforcement off on the very connection that drops.
    is_sqlite = engine.dialect.name == "sqlite"
    with engine.connect() as connection:
        if is_sqlite:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        Base.metadata.drop_all(bind=connection)
        if is_sqlite:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()
    Base.metadata.create_all(engine)
    apply_immutable_triggers(engine)
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture
def store(tmp_path):
    return LocalFilesystemStore(root=tmp_path)


def import_release(db, source, path, store=None):
    xml = path.read_bytes()
    run, replayed = import_release_bytes(db, source=source, xml=xml, store=store)
    db.commit()
    return run, replayed


@pytest.fixture
def source(session):
    src, _ = get_or_create_source(session, **SOURCE)
    session.commit()
    return src


@pytest.fixture
def corpus(session, source, store):
    """Both fixture releases imported (release 2 observes release 1's
    unchanged article versions)."""
    run1, _ = import_release(session, source, RELEASE_1, store)
    run2, _ = import_release(session, source, RELEASE_2, store)
    return {"run1": run1, "run2": run2}


@pytest.fixture
def client(session):
    from app.api.deps import get_db
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_db] = lambda: session
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


# --- LEGI mini corpus fixture (real DILA fiches) ---------------------------
LEGI_MINI_DIR = REPO_ROOT / "tests" / "fixtures" / "legi-code-civil-mini"
LEGI_TEXTe_CID = "LEGITEXT000006070721"


@pytest.fixture
def legi_run(session, tmp_path):
    from app.ingestion.legi_adapter import LEGI_SOURCE
    from app.ingestion.legi_service import import_legi_release
    from app.sources.service import get_or_create_source

    source, _ = get_or_create_source(session, **LEGI_SOURCE)
    run, replayed = import_legi_release(
        session,
        source=source,
        texte_cid=LEGI_TEXTe_CID,
        base_dir=LEGI_MINI_DIR,
        release_label="Freemium_legi_global_20261108-140000.tar.gz",
        store=LocalFilesystemStore(root=tmp_path),
    )
    session.commit()
    return run


@pytest.fixture
def benchmark_stats():
    """Shared dict collecting the printed measures of a benchmark run."""
    return {}
