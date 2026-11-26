"""API contract tests (category 7): the live application honours the V1
contract published in the archive (docs/spec/openapi.yaml) — every
documented path exists, with the documented parameters — plus pagination
correctness over a full traversal and consistent error codes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

SPEC = Path(__file__).resolve().parents[2] / "docs" / "spec" / "openapi.yaml"


@pytest.fixture(scope="module")
def contract_spec() -> dict:
    return yaml.safe_load(SPEC.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def contract_client():
    """A module-scoped client: contract checks need no corpus, but a small
    one keeps list endpoints realistic."""
    from fastapi.testclient import TestClient

    from app.db.base import Base
    from app.db.session import get_engine
    from app.db.triggers import apply_immutable_triggers
    from app.main import create_app

    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    apply_immutable_triggers(engine)
    app = create_app()
    with TestClient(app) as client:
        yield client
    Base.metadata.drop_all(engine)


def test_every_contracted_path_is_served(contract_client, contract_spec):
    """Chaque chemin documenté dans l'archive doit exister sur l'application
    réelle. fastapi ≥ 0.165 monte les routers en différé (_IncludedRouter):
    la surface réellement servie se lit dans /openapi.json."""
    served = contract_client.get("/openapi.json").json()["paths"]
    served_normalized = {p.lower() for p in served}

    base = ""
    for server in contract_spec.get("servers", []):
        if server.get("url"):
            base = server["url"].rstrip("/").lower()
            break

    for spec_path in contract_spec["paths"]:
        live = f"{base}{spec_path.lower()}"
        assert live in served_normalized, (
            f"contracted path missing from the live API: {spec_path} "
            f"(expected {live})"
        )


def test_contracted_query_parameters_are_accepted(contract_client, contract_spec):
    """Paramètres documentés: sans erreur de validation (leurs valeurs
    obtiennent un traitement défini : 200, 404 ou 400 métier — jamais 422
    ou 500)."""
    cases = [
        ("/v1/documents", {"jurisdiction": "zz", "document_type": "code", "q": "x"}),
        ("/v1/documents", {"limit": 1, "cursor": "not-a-cursor"}),
        ("/v1/nodes/lg:fr:none:article:1/diff", {"from": "a", "to": "b"}),
        ("/v1/documents/lg:fr:none/changes", {"from": "a", "to": "b"}),
    ]
    for path, params in cases:
        response = contract_client.get(path, params=params)
        assert response.status_code < 500, (
            f"{path} crashed on documented parameters {params}"
        )
        assert response.status_code != 422, f"{path} rejects a documented parameter"


def test_error_object_shape_is_contractual(contract_client):
    """{code, message, details?} sur toutes les erreurs, jamais d'autre
    forme (contrat de la spec API_CONTRACT)."""
    for path in (
        "/v1/documents/lg:fr:inconnu:xx",
        "/v1/nodes/lg:fr:inconnu:article:1",
        "/v1/sources/inconnu",
        "/v1/exports/inconnu",
        "/v1/nodes/lg:fr:x:article:1/versions/lgv:fr:x:article:1:none",
    ):
        response = contract_client.get(path)
        assert response.status_code == 404, path
        body = response.json()
        assert set(body) <= {"code", "message", "details"}, body
        assert body["code"] == "not_found"


def test_validation_errors_use_the_contract_shape(contract_client):
    response = contract_client.get("/v1/documents", params={"limit": "abc"})
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_openapi_json_documents_the_served_surface(contract_client):
    spec = contract_client.get("/openapi.json").json()
    served = set(spec["paths"].keys())
    # Every GET operation of the published contract appears in the live
    # openapi document (the served surface documents itself).
    import yaml

    archived = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    base = archived["servers"][0]["url"].rstrip("/")
    for path, item in archived["paths"].items():
        assert f"{base}{path}" in served


class TestPaginationContract:
    """Pagination complète: traversal with next_cursor recovers every item
    exactly once, has_more/next_cursor consistent at each step."""

    @pytest.fixture(scope="class")
    def populated(self):
        """Large volume for pagination: 250 synthetic documents (identity
        determinism at scale + cursor traversal over a real volume)."""
        from sqlalchemy import func, select

        from app.canonical import service as canonical
        from app.canonical.models import Document
        from app.db.session import get_session_factory
        from app.sources.models import Source

        factory = get_session_factory()
        session = factory()
        try:
            if session.get(Source, "pagination-source") is None:
                session.add(
                    Source(
                        id="pagination-source",
                        name="Pagination corpus",
                        publisher=None,
                        jurisdiction="fr",
                        source_type="official_dataset",
                    )
                )
                session.flush()
            total = session.scalar(
                select(func.count()).select_from(Document.__table__)
            )
            existing = total if total else 0
            for i in range(existing, 250):
                canonical.get_or_create_document(
                    session,
                    source_id="pagination-source",
                    jurisdiction="fr",
                    slug=f"code-essais-{i:03d}",
                    title=f"Code d'essais {i:03d}",
                    document_type="code",
                )
            session.commit()
            yield 250
        finally:
            session.close()

    def test_traversal_recovers_250_documents_exactly_once(self, populated):
        from fastapi.testclient import TestClient

        from app.api.deps import get_db
        from app.db.session import get_session_factory
        from app.main import create_app

        app = create_app()
        session = get_session_factory()()
        app.dependency_overrides[get_db] = lambda: session
        with TestClient(app) as client:
            seen = []
            cursor = None
            steps = 0
            while True:
                params = {"limit": 17}  # non-round page size on purpose
                if cursor:
                    params["cursor"] = cursor
                body = client.get("/v1/documents", params=params).json()
                seen.extend(item["id"] for item in body["items"])
                steps += 1
                if not body["has_more"]:
                    assert body["next_cursor"] is None
                    break
                assert body["next_cursor"]
                cursor = body["next_cursor"]
                assert steps < 100, "pagination loop runaway"
            assert len(seen) == 250
            assert len(set(seen)) == 250, "pagination never duplicates items"
            # Page boundaries respected: page content sizes match the limit
            # except the last one (250 = 14x17 + 12 -> 15 pages).
            assert steps == 15
