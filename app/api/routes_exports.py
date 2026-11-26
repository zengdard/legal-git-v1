"""Bulk corpus export (NDJSON) endpoints and manifests (docs/exports.md)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from app.api.deps import SessionDep
from app.api.errors import ApiError
from app.canonical.models import Document
from app.exports.service import build_ndjson, corpus_manifest

router = APIRouter(prefix="/exports", tags=["exports"])

NDJSON_MEDIA_TYPE = "application/x-ndjson"


@router.get("")
def list_export_manifests(session: SessionDep) -> dict:
    return {"items": corpus_manifest(session)}


@router.get("/{corpus_id}")
def download_export(corpus_id: str, session: SessionDep) -> Response:
    """Streams the corpus as NDJSON: one JSON record per line (manifest,
    document, node, node_version, relationship).

    The response carries X-LegalGit-Export-Sha256, the sha256 of the body, so
    consumers can verify the download.
    """
    document = session.get(Document, corpus_id)
    if document is None:
        raise ApiError(404, "not_found", f"corpus {corpus_id!r} not found")
    payload, digest = build_ndjson(session, document)
    return Response(
        content=payload,
        media_type=NDJSON_MEDIA_TYPE,
        headers={
            "X-LegalGit-Export-Sha256": f"sha256:{digest}",
            "Content-Disposition": f'attachment; filename="{corpus_id}.ndjson"',
        },
    )
