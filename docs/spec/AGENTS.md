# Instructions for coding agents

You are implementing Legal Git V1, a neutral legal-document infrastructure for developers.

## Hard product boundaries

- Build a document database, not a legal assistant.
- Preserve source content; do not paraphrase, summarize, interpret, or silently normalize legal text.
- Do not infer legal obligations, permissions, prohibitions, or legal consequences.
- Do not implement AST parsing, semantic extraction, or a rule engine in V1.
- Do not present Legal Git as the legally authoritative publisher. Store provenance back to official sources.
- Do not fabricate dates, source identifiers, document hierarchy, or historical versions.
- If upstream data is incomplete or ambiguous, preserve the raw source and record the limitation.

## Core invariants

1. A logical document ID identifies the document across versions.
2. A node ID identifies a logical structural element across versions where continuity can be established.
3. A version is immutable once ingested.
4. Every version is tied to a source record and an ingestion timestamp.
5. Every fragment offset is scoped to one exact node version and one exact content representation.
6. The original source text and punctuation must be preserved byte-for-byte where feasible; if decoding or source-format conversion is required, document the transformation and preserve the raw artifact.
7. A diff compares two explicit versions. Never imply that a diff itself is a legal interpretation.
8. A source identifier is not the same thing as a Legal Git identifier.
9. Hierarchical parent-child relationships are distinct from cross-references and citations.
10. Do not use mutable content as the identity of a document or node.

## Engineering guidance

- Prefer a modular monolith for V1.
- Recommended stack: Python + FastAPI, PostgreSQL, object storage abstraction (local filesystem in development; S3-compatible in deployment).
- Use relational tables and adjacency relationships in PostgreSQL. Do not introduce a graph database in V1.
- Publish an OpenAPI specification.
- Keep ingestion adapters separate from the canonical data model.
- Store raw upstream payloads or source packages when licensing and operational constraints permit.
- Make ingestion idempotent.
- Add tests for hierarchy, identity, version immutability, offset validity, diff behavior, and provenance.
- Do not build a Git repository per article. Use immutable database snapshots/versions and expose Git-like commits/diffs at the API level.

## Working protocol

Before implementing a feature:
1. Identify the relevant requirement in the specification.
2. Check whether it is in V1 scope.
3. Add or update tests.
4. Implement the smallest complete behavior.
5. Update API/schema documentation.
6. Report assumptions and upstream data limitations.

If a requirement conflicts with the V1 boundary, do not silently implement it. Flag it for product review.
