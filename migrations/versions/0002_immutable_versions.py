"""node_versions immutability trigger (DB-level guard)

Revision ID: 0002_immutable_versions
Revises: 0001_initial
Create Date: 2026-11-23

Immutability is now enforced at the database level in addition to the ORM
guard: any UPDATE or DELETE against node_versions aborts with a clear
error. Corrections to ingestion must create new versions, never rewrite
history.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_immutable_versions"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

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

CREATE TRIGGER trg_node_versions_immutable
BEFORE UPDATE OR DELETE ON node_versions
FOR EACH ROW
EXECUTE FUNCTION legalgit_block_node_version_mutation();
"""

PG_UNDO = """
DROP TRIGGER IF EXISTS trg_node_versions_immutable ON node_versions;
DROP FUNCTION IF EXISTS legalgit_block_node_version_mutation();
"""

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

SQLITE_UNDO = [
    "DROP TRIGGER IF EXISTS trg_node_versions_immutable_update",
    "DROP TRIGGER IF EXISTS trg_node_versions_immutable_delete",
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(PG_TRIGGER)
    else:
        for statement in SQLITE_TRIGGERS:
            op.execute(statement)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(PG_UNDO)
    else:
        for statement in SQLITE_UNDO:
            op.execute(statement)
