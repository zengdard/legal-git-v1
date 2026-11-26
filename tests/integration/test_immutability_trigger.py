"""Database-level immutability: triggers block raw SQL mutations of
node_versions, complementing the ORM guard (acceptance criteria C:
"existing version content cannot be silently overwritten", extended from
the ORM scope to the database itself)."""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select, text, update

from app.canonical.models import NodeVersion


def test_raw_sql_update_is_blocked_by_trigger(session, corpus):
    version = session.scalars(select(NodeVersion)).first()
    with pytest.raises(Exception, match="(?i)immutable"):
        session.execute(
            update(NodeVersion).where(NodeVersion.id == version.id).values(
                content="texte corrompu"
            )
        )
    session.rollback()


def test_raw_sql_delete_is_blocked_by_trigger(session, corpus):
    version = session.scalars(select(NodeVersion)).first()
    with pytest.raises(Exception, match="(?i)immutable"):
        session.execute(delete(NodeVersion).where(NodeVersion.id == version.id))
    session.rollback()


def test_raw_delete_via_text_is_blocked(session, corpus):
    version = session.scalars(select(NodeVersion)).first()
    with pytest.raises(Exception, match="(?i)immutable"):
        session.execute(
            text("DELETE FROM node_versions WHERE id = :id"),
            {"id": version.id},
        )
    session.rollback()


def test_version_api_has_no_delete_path():
    """No service function exposes deletion of versions."""
    from app.versioning import service as versioning

    updaters = [
        name
        for name in dir(versioning)
        if not name.startswith("_") and ("delete" in name or "remove" in name)
    ]
    assert updaters == []
