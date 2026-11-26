"""Legal Git API — FastAPI application factory."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import (
    routes_documents,
    routes_exports,
    routes_nodes,
    routes_sources,
)
from app.api.errors import install_error_handlers
from app.config import settings
from app.db.session import get_engine
from app.versioning.service import install_immutability_guard


def create_app() -> FastAPI:
    install_immutability_guard()

    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description=(
            "Structured, hierarchical, versioned legal-document data for "
            "developers. Legal Git is a normalized technical representation "
            "with traceable provenance; official publication sources remain "
            "authoritative. A diff is a textual/structural change record, "
            "never a legal interpretation."
        ),
    )
    install_error_handlers(app)

    # Observability: HTTP_REQUESTS counter middleware + /metrics.
    from starlette.middleware.base import BaseHTTPMiddleware

    from app import observability

    class _MetricsMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            observability.HTTP_REQUESTS.labels(
                method=request.method,
                path=request.scope.get("route").path
                if request.scope.get("route")
                else request.url.path,
                status=str(response.status_code),
            ).inc()
            return response

    app.add_middleware(_MetricsMiddleware)

    @app.get("/metrics", tags=["ops"], summary="Prometheus metrics")
    def metrics() -> Response:
        from fastapi.responses import PlainTextResponse

        return PlainTextResponse(
            content=observability.render_metrics().decode("utf-8"),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    v1 = APIRouter(prefix="/v1")
    v1.include_router(routes_documents.router)
    v1.include_router(routes_nodes.router)
    v1.include_router(routes_sources.router)
    v1.include_router(routes_exports.router)
    app.include_router(v1)

    @app.get("/healthz", tags=["ops"], summary="Liveness")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz", tags=["ops"], summary="Readiness (DB + native core)")
    def readyz() -> JSONResponse:
        try:
            with get_engine().connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(
                status_code=503,
                content={"status": "unavailable", "database": "down"},
            )
        from app.core import ensure_native_module

        native = ensure_native_module()
        return {"status": "ok", "database": "ok", **native}

    return app


app = create_app()
