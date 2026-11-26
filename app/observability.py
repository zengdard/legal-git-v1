"""Basic observability: Prometheus-format metrics (docs/operations.md).

Counters: HTTP requests by method/path-template/status.
Gauges (refreshed on scrape): ingestion runs, node versions, node version
observations — the corpus state, from the canonical database.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest
from sqlalchemy import func, select

from app.canonical.models import NodeVersion, NodeVersionObservation
from app.db.session import get_engine
from app.sources.models import IngestionRun

registry = CollectorRegistry(auto_describe=False)

HTTP_REQUESTS = Counter(
    "legalgit_http_requests_total",
    "HTTP requests handled, by method, path and status.",
    labelnames=("method", "path", "status"),
    registry=registry,
)

INGESTION_RUNS = Gauge(
    "legalgit_ingestion_runs",
    "Ingestion runs recorded (all statuses).",
    registry=registry,
)
NODE_VERSIONS = Gauge(
    "legalgit_node_versions",
    "Immutable node versions stored.",
    registry=registry,
)
NODE_VERSION_OBSERVATIONS = Gauge(
    "legalgit_node_version_observations",
    "Version observations across ingestion runs.",
    registry=registry,
)


def _refresh_gauges() -> None:
    """Refreshes the gauges from the canonical database; never raises into
    the scrape path (a database hiccup yields stale metrics, not a 500)."""
    try:
        engine = get_engine()
        with engine.connect() as connection:
            INGESTION_RUNS.set(
                connection.scalar(select(func.count()).select_from(IngestionRun.__table__)) or 0
            )
            NODE_VERSIONS.set(
                connection.scalar(select(func.count()).select_from(NodeVersion.__table__)) or 0
            )
            NODE_VERSION_OBSERVATIONS.set(
                connection.scalar(
                    select(func.count()).select_from(NodeVersionObservation.__table__)
                )
                or 0
            )
    except Exception:  # noqa: BLE001 - metrics must never break the app
        pass


def render_metrics() -> bytes:
    _refresh_gauges()
    return generate_latest(registry)
