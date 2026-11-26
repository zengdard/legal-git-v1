# Implementation plan — Legal Git V1

Build in small vertical slices. Do not begin with every jurisdiction or every legal source.

## Phase 0 — Repository foundation
- Set up application, configuration and environment handling.
- Docker Compose for API + PostgreSQL.
- Database migrations.
- Health/readiness endpoints.
- CI with formatting, linting and tests.
- Seed development data.

Exit: a developer can run the service locally from documented instructions.

## Phase 1 — Canonical model
- Implement Source, IngestionRun, Document, Node, NodeVersion, Relationship and identity mapping.
- Add constraints and indexes.
- Add hierarchy traversal.
- Add content hashing and immutable-version behavior.

Exit: test fixtures can create a document tree and multiple versions without violating invariants.

## Phase 2 — First source adapter
- Select and document the official Code civil source package/API.
- Preserve raw source artifacts where permitted.
- Parse source format.
- Map source metadata and hierarchy into canonical entities.
- Make ingestion idempotent.
- Produce import report with counts, skipped records and errors.

Exit: repeat import does not create duplicate logical entities or duplicate versions.

## Phase 3 — Read API
- Documents list/detail.
- Document tree.
- Node detail/children.
- Node versions and version detail.
- Source detail.
- Pagination and error model.

Exit: a separate sample client can retrieve a Code civil article and its hierarchy.

## Phase 4 — Versioning and diffs
- Compare two explicit node versions.
- Return machine-readable changes and ranges.
- Add document snapshot comparison if upstream release model supports it.
- Preserve provenance on both sides.

Exit: tests prove a changed comma, word or paragraph is detectable and offsets map to the exact version representation.

## Phase 5 — Fragment addressing and exports
- Implement version-scoped fragment endpoint.
- Declare offset unit and representation.
- JSONL/NDJSON export.
- Export manifest and checksums.

Exit: external developer can download and process the pilot corpus.

## Phase 6 — Hardening and developer experience
- OpenAPI review.
- Quickstart and code examples.
- Rate limiting/authentication decision.
- Ingestion monitoring.
- Backup and restore test.
- Performance baseline.
- Validate source coverage and licensing notes.

Exit: a developer outside the core team can use the API without one-to-one assistance.

## Suggested repository structure

```text
legal-git/
  app/
    api/
    canonical/
    sources/
    ingestion/
    versioning/
    exports/
    db/
    config.py
    main.py
  migrations/
  tests/
    unit/
    integration/
    fixtures/
  docs/
  scripts/
  examples/
  docker-compose.yml
  pyproject.toml
  README.md
  AGENTS.md
```

## Do not optimize prematurely

- No microservices.
- No Neo4j.
- No vector database.
- No Git repository per article.
- No LLM-based semantic extraction.
- No rule engine.
- No complex billing.
