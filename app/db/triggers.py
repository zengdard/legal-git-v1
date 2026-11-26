"""Shared DDL snippets: database-level immutability guard.

The authoritative copy lives in migrations/versions/0002_immutable_versions.py;
this helper lets tests apply the same triggers on schemas created via
metadata.create_all (fast path).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

SQLITE_TRIGGERS = [
    """
    CREATE TRIGGER IF NOT EXISTS trg_node_versions_immutable_update
    BEFORE UPDATE ON node_versions
    BEGIN
        SELECT RAISE(ABORT, 'node_versions rows are immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_node_versions_immutable_delete
    BEFORE DELETE ON node_versions
    BEGIN
        SELECT RAISE(ABORT, 'node_versions rows are immutable');
    END
    """,
]

PG_TRIGGER = """
CREATE OR REPLACE FUNCTION legalgit_block_node_version_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'node_versions rows are immutable (id=%)',
        coalesce(OLD.id, NEW.id)
    USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_node_versions_immutable ON node_versions;

CREATE TRIGGER trg_node_versions_immutable
BEFORE UPDATE OR DELETE ON node_versions
FOR EACH ROW
EXECUTE FUNCTION legalgit_block_node_version_mutation();
"""


def apply_immutable_triggers(engine: Engine) -> None:
    """Applies the node_versions immutability triggers (idempotent)."""
    if engine.url.get_backend_name() == "postgresql":
        statements = [PG_TRIGGER]
    else:
        statements = SQLITE_TRIGGERS
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
