"""Source registry entities: upstream sources and ingestion runs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow

# Portable JSON type across SQLite (dev/tests) and PostgreSQL (deployment).
JSONType = sqlite.JSON().with_variant(postgresql.JSONB(), "postgresql")


class Source(Base):
    """An upstream publisher, dataset or source release channel."""

    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(512))
    publisher: Mapped[str | None] = mapped_column(String(512))
    jurisdiction: Mapped[str] = mapped_column(String(8))
    source_type: Mapped[str] = mapped_column(String(64))
    base_uri: Mapped[str | None] = mapped_column(Text)
    licence_name: Mapped[str | None] = mapped_column(String(255))
    licence_uri: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class IngestionRun(Base):
    """One retrieval/import of a source release.

    A "document snapshot" in the public API corresponds to one ingestion
    run (the import batch that groups the node versions observed together).
    """

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "upstream_release_id", "checksum", name="uq_run_release"
        ),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("sources.id"), nullable=False
    )
    upstream_release_id: Mapped[str | None] = mapped_column(String(255))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    raw_artifact_uri: Mapped[str | None] = mapped_column(Text)
    checksum: Mapped[str | None] = mapped_column(String(128))
    report: Mapped[dict] = mapped_column(JSONType, default=dict)
