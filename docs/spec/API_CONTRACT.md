# API contract — Legal Git V1

Base path: `/v1`

The API is read-oriented for consumers. Ingestion endpoints should be internal/admin-only and are not required in the public V1 contract.

## Core endpoints

### Documents
- `GET /documents`
  - filters: `jurisdiction`, `document_type`, `source_id`, `q`
  - pagination: `limit`, `cursor`
- `GET /documents/{document_id}`
- `GET /documents/{document_id}/tree`
- `GET /documents/{document_id}/versions` (document snapshots/import releases where implemented)

### Nodes
- `GET /nodes/{node_id}`
- `GET /nodes/{node_id}/children`
- `GET /nodes/{node_id}/versions`
- `GET /nodes/{node_id}/versions/{version_id}`

### Diffs
- `GET /nodes/{node_id}/diff?from={version_id}&to={version_id}`
- `GET /documents/{document_id}/changes?from={snapshot_id}&to={snapshot_id}`

### Sources
- `GET /sources`
- `GET /sources/{source_id}`

### Fragments
- `GET /node-versions/{version_id}/fragment?start={n}&end={n}&representation={id}`

### Exports
- `GET /exports/{corpus_id}` or a documented export manifest/download flow.

## Response conventions

- JSON responses.
- Stable IDs in all entity responses.
- Dates are ISO 8601.
- Include `source` and `provenance` information where relevant.
- Use explicit nulls for unavailable values where useful; do not fabricate.
- Paginated list responses include `items`, `next_cursor` and `has_more`.
- Errors use a consistent object: `code`, `message`, optional `details`.

## Example node version response

```json
{
  "id": "lgv:fr:cc:article-1103:example-version",
  "node_id": "lg:fr:code-civil:article:1103",
  "source_id": "legifrance",
  "content": "Les contrats légalement formés tiennent lieu de loi à ceux qui les ont faits.",
  "content_format": "plain_text",
  "content_hash": "sha256:...",
  "representation_id": "plain-text-v1",
  "valid_from": null,
  "valid_to": null,
  "published_at": null,
  "effective_from": null,
  "effective_to": null,
  "ingested_at": "2026-01-01T12:00:00Z",
  "provenance": {
    "upstream_id": null,
    "source_uri": null,
    "ingestion_run_id": "ingest-example"
  }
}
```

All IDs and metadata above are illustrative. Do not hardcode example dates or upstream identifiers into production data.

## Diff response shape

A diff should include:
- `node_id`
- `from_version_id`
- `to_version_id`
- `algorithm`
- `representation_id`
- `changes` with operation and old/new ranges or text
- `source_provenance` for both versions

Operations may include `insert`, `delete`, `replace`. Structural diff may additionally include `node_added`, `node_removed`, `node_moved`, `metadata_changed`.

## Semantics

- `valid_from` / `valid_to` describe legal validity only when the source supports them.
- `published_at` is not equivalent to `effective_from`.
- An ingestion timestamp is not a legal date.
- A diff does not state whether a change is legally material.
- A fragment is an exact address into a selected version, not an interpreted legal unit.
