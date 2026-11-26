# Legal Git — V1 implementation archive

This archive is the product and engineering handoff for **Legal Git V1**.

## Product definition

Legal Git V1 is a **structured, hierarchical, versioned legal-document data layer for developers**.

It provides:
- legal sources and source provenance;
- documents and their hierarchical nodes;
- stable identifiers for logical documents and nodes;
- immutable versions of node content;
- exact source text preservation;
- fragment addressing through offsets within a specific version;
- change detection and diffs between versions;
- a developer-facing API and bulk export.

Developers use this foundation to build their own products: legal search, AI agents, compliance systems, rule extraction, regulatory monitoring, and other applications.

## Non-goals for V1

Do **not** build:
- a legal chatbot or legal assistant;
- legal advice or legal interpretation;
- automated extraction or validation of legal obligations;
- an AST or semantic legal graph;
- a rule engine or compliance execution engine;
- collaborative legal editing;
- contract lifecycle management;
- a legal research UI intended for lawyers.

The data model should make future extensions possible, but V1 must remain a neutral data infrastructure product.

## Recommended first corpus

Start with a narrow, testable corpus:
- jurisdiction: France (`FR`);
- source: official Légifrance / DILA open data;
- corpus: Code civil;
- include the current consolidated structure and historical versions where the upstream source makes them available.

Do not claim that Legal Git replaces the official publication source. The official source remains authoritative. Legal Git is a normalized, developer-friendly technical representation with traceable provenance.

## Read order for coding agents

1. `AGENTS.md` — operating rules for agents.
2. `PRODUCT_SPEC.md` — what to build and what not to build.
3. `ARCHITECTURE.md` — system boundaries and technical design.
4. `DATA_MODEL.md` — entities, identifiers, versioning and invariants.
5. `API_CONTRACT.md` and `openapi.yaml` — API behavior.
6. `IMPLEMENTATION_PLAN.md` — suggested build sequence.
7. `ACCEPTANCE_CRITERIA.md` — definition of done.
8. `examples/` — illustrative payloads.

## Status of this specification

This is an implementation-oriented V1 proposal, not a claim that all upstream legal datasets expose every field in the same way. Build source adapters that preserve the upstream identifiers and metadata when available, and record missing or unavailable fields explicitly. Never fabricate source facts.
