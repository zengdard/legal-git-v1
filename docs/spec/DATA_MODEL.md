# Canonical data model — Legal Git V1

This document defines the minimum canonical entities. Field names can be adapted to implementation conventions, but semantics should remain stable.

## 1. Source

Represents an upstream publisher, dataset or source release.

Suggested fields:
- `id` (stable internal ID)
- `name`
- `publisher`
- `jurisdiction`
- `source_type` (official_api, official_dataset, publisher_site, etc.)
- `base_uri` (nullable)
- `licence_name` (nullable)
- `licence_uri` (nullable)
- `created_at`

A retrieval/import is a separate `IngestionRun`:
- `id`
- `source_id`
- `upstream_release_id` (nullable)
- `retrieved_at`
- `started_at`
- `completed_at`
- `status`
- `raw_artifact_uri` (nullable)
- `checksum` (nullable)
- `report` (JSON)

## 2. Document

Represents the logical legal instrument.

Suggested fields:
- `id` (Legal Git stable ID)
- `jurisdiction`
- `document_type`
- `title`
- `official_identifier` (nullable)
- `source_id`
- `upstream_id` (nullable)
- `publication_date` (nullable)
- `promulgation_date` (nullable)
- `status` (nullable)
- `metadata` (JSON)
- `created_at`

Do not use one date field to represent several legal date concepts.

## 3. Node

Represents a structural element within a document.

Suggested fields:
- `id`
- `document_id`
- `parent_id` (nullable)
- `node_type`
- `label` (nullable)
- `identifier` (nullable; e.g. article number)
- `sort_order`
- `upstream_id` (nullable)
- `metadata` (JSON)
- `created_at`

A node is a logical identity, not a specific text version.

## 4. NodeVersion

Represents the exact content of a node at a particular source/version state.

Suggested fields:
- `id`
- `node_id`
- `source_id`
- `ingestion_run_id`
- `upstream_version_id` (nullable)
- `content`
- `content_format` (plain_text, xml_fragment, html, etc.)
- `content_hash`
- `representation_id`
- `valid_from` (nullable)
- `valid_to` (nullable)
- `published_at` (nullable)
- `effective_from` (nullable)
- `effective_to` (nullable)
- `ingested_at`
- `raw_payload_uri` (nullable)
- `metadata` (JSON)

Immutability: content and source facts are immutable after creation. A new observed state creates a new NodeVersion.

## 5. Relationship

Represents a non-hierarchical link between documents or nodes.

Suggested fields:
- `id`
- `from_node_id` (nullable)
- `from_document_id` (nullable)
- `to_node_id` (nullable)
- `to_document_id` (nullable)
- `relationship_type`
- `source_id` (nullable)
- `evidence` (nullable)
- `metadata` (JSON)

Examples: `refers_to`, `cites`, `amends`, `repeals`, `implements`, `related_to`.

Do not treat a textual cross-reference as proof of a legal effect unless the source explicitly establishes that effect.

## 6. Fragment addressing

A fragment can initially be an API-level address rather than a separately persisted entity.

Minimum address:
- `node_version_id`
- `representation_id`
- `start_offset`
- `end_offset`
- `offset_unit`

The API must validate:
- `0 <= start_offset <= end_offset <= content_length`;
- representation matches the selected version;
- offsets use the declared coordinate system.

Optional persisted `Fragment` table:
- `id`
- `node_version_id`
- `representation_id`
- `start_offset`
- `end_offset`
- `label` (neutral, optional)
- `metadata`

Do not add semantic labels such as obligation or exception in V1.

## 7. Identity mapping

Maintain a mapping between external IDs and canonical IDs:
- `id`
- `entity_type`
- `canonical_id`
- `source_id`
- `upstream_id`
- `first_seen_at`
- `last_seen_at`

This supports stable identity when source-specific identifiers differ.

## 8. Invariants and constraints

- Unique canonical IDs.
- Unique `(source_id, entity_type, upstream_id)` when upstream ID is present.
- A node's parent belongs to the same document.
- No hierarchy cycles.
- Stable sibling ordering.
- A node version belongs to an existing node.
- A node version's content hash matches its stored content representation.
- A version's source and ingestion run are traceable.
- Historical node versions are immutable.
- `valid_to` must be after `valid_from` when both are known.
- Fragment offsets must fit the exact selected representation.
