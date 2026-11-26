# Architecture — Legal Git V1

## 1. System boundary

Legal Git V1 is a data ingestion, normalization, storage and delivery system.

```text
Official source / dataset
        |
        v
Source adapter
        |
        v
Raw artifact store -----> ingestion log
        |
        v
Parser / source mapper
        |
        v
Canonical model
  - Source
  - Document
  - Node
  - NodeVersion
  - Relationship
        |
        v
PostgreSQL + object storage
        |
        +---- REST API
        +---- Version/diff service
        +---- Bulk export
```

The parser in this diagram is a source-format parser (XML/JSON/ZIP etc.), not a legal-language parser.

## 2. Recommended V1 stack

- Python 3.12+ (or current supported Python release)
- FastAPI
- PostgreSQL
- SQLAlchemy or SQLModel (choose one; avoid mixing ORM patterns)
- Alembic migrations
- Pydantic schemas
- pytest
- Object storage abstraction:
  - local filesystem for development;
  - S3-compatible storage in deployment.
- Docker Compose for local development.

These are recommended defaults, not immutable product requirements.

## 3. Modules

### `sources`
Source registry, licences, upstream identifiers and retrieval metadata.

### `ingestion`
Download/import jobs, raw artifact retention, idempotency, validation and import reports.

### `canonical`
Canonical Document, Node, NodeVersion and Relationship models.

### `versioning`
Content hashing, immutable version records, version listing and diff generation.

### `api`
REST endpoints, pagination, filtering, response schemas and OpenAPI.

### `exports`
JSONL/NDJSON corpus exports and export manifests.

## 4. Data storage

Use PostgreSQL for canonical metadata and relationships.

Use object storage for:
- raw source packages;
- large XML/JSON source artifacts;
- large version payloads if database storage is not appropriate;
- generated corpus exports.

For a small pilot, content can initially be stored in PostgreSQL. Keep a storage interface so this can change without rewriting domain logic.

## 5. Identity strategy

Legal Git IDs must be deterministic and independent of content.

Preferred strategy:
- use stable upstream identifiers when available, namespaced by jurisdiction and source;
- otherwise derive an ID from a documented canonical path and document identity;
- persist an explicit mapping table between upstream IDs and Legal Git IDs.

Do not generate IDs from article text or content hashes. Text changes must not change the logical identity of an article when continuity is established.

Example (illustrative namespace, not official):
- `lg:fr:code-civil`
- `lg:fr:code-civil:article:1103`

If an article is renumbered, split, merged or replaced, do not silently reuse identity. Record explicit relationships such as `renumbered_to`, `split_into`, `merged_into` or `replaced_by` only when supported by source evidence or reviewed mapping.

## 6. Hierarchy and relationships

Parent-child hierarchy:
- one parent node may have many child nodes;
- child ordering is explicit;
- hierarchy can differ by document/source;
- preserve source order.

Cross-document relationships are separate:
- cites;
- refers_to;
- amends;
- repeals;
- implements;
- related_to.

Only populate relationship types supported by source data or deterministic source mapping. Do not infer legal effects in V1.

## 7. Versioning model

A logical Node has one or more immutable NodeVersion records.

Each NodeVersion:
- belongs to exactly one Node;
- has a unique version ID;
- records source and ingestion metadata;
- stores content hash and content payload/reference;
- can have validity/effectivity metadata when supplied.

Never update an old NodeVersion's content. Corrections to ingestion should create a corrected ingestion record/version and preserve auditability.

A “document snapshot” may be represented as a source release/import batch that groups the node versions observed in one upstream release.

## 8. Diff strategy

V1 can use:
- line-based diff for readable text;
- character/token range diff for precise machine-readable changes;
- structural diff for node additions, removals, moves and metadata changes.

Return old/new version IDs and changed ranges. State the algorithm and coordinate system in the API. Do not call the output a legal impact assessment.

## 9. Fragment offsets

Choose one canonical offset coordinate system and document it. Recommendation: Unicode code-point offsets over the exact decoded text string returned by the API, with content hash and representation ID included.

If the source provides byte offsets or markup offsets, preserve those separately rather than pretending they are equivalent.

Offsets are version-scoped. Never apply offsets from V2 to V3 without a mapping or recalculation.

## 10. Security and operations

- Validate all imported source packages.
- Avoid executing content from source files.
- Set upload/download size limits.
- Log ingestion provenance and failures.
- Keep API keys/authentication simple for the pilot; public read-only access can be considered later.
- Apply rate limiting before public production.
- Back up PostgreSQL and object storage.
- Provide health and readiness endpoints.
