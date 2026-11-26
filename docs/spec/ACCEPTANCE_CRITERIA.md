# Acceptance criteria — Legal Git V1

## A. Ingestion and provenance
- [ ] An ingestion run identifies its source and retrieval time.
- [ ] Raw source artifact is retained or its retention limitation is documented.
- [ ] Imported records retain upstream identifiers where available.
- [ ] Import report includes counts, failures and skipped/unsupported records.
- [ ] Re-running the same source release is idempotent.

## B. Canonical hierarchy
- [ ] A document can contain an ordered hierarchy of nodes.
- [ ] Each node has a stable canonical ID.
- [ ] Each node points to its document and optional parent.
- [ ] Parent-child relationships cannot cross documents.
- [ ] Cycles are rejected.
- [ ] Source order is preserved.
- [ ] Cross-references are stored separately from parent-child hierarchy.

## C. Version integrity
- [ ] A node can have multiple immutable versions.
- [ ] A version is traceable to source and ingestion run.
- [ ] Content hash is reproducible.
- [ ] Existing version content cannot be silently overwritten.
- [ ] Legal dates are represented separately and may be null.
- [ ] The system does not invent historical versions when source history is unavailable.

## D. Text and fragments
- [ ] Original text and punctuation are preserved in the canonical representation.
- [ ] Content representation and offset unit are explicit.
- [ ] Fragment offsets are scoped to a specific version.
- [ ] Invalid or out-of-range offsets are rejected.
- [ ] An offset from one version is not assumed valid in another version.

## E. Diffs
- [ ] Two explicit versions can be compared.
- [ ] Insertions, deletions and replacements are returned.
- [ ] A punctuation-only change is detectable.
- [ ] The response identifies both compared versions.
- [ ] The diff is not labelled as legal interpretation or impact assessment.

## F. API and developer experience
- [ ] API exposes document list/detail.
- [ ] API exposes document hierarchy.
- [ ] API exposes node detail and versions.
- [ ] API exposes source provenance.
- [ ] API exposes version diff.
- [ ] API supports pagination for collections.
- [ ] OpenAPI documentation is available.
- [ ] Quickstart includes at least one working request.
- [ ] Bulk export is documented and machine-readable.

## G. Pilot validation
- [ ] Code civil pilot corpus is imported with a documented coverage statement.
- [ ] At least one external developer can retrieve an article and its hierarchy.
- [ ] At least one external developer can compare two source-backed versions where available.
- [ ] External developer can use the export without writing a parser for the original source package.

## Explicitly not required for V1
- [ ] AST or syntactic parse.
- [ ] Legal obligation extraction.
- [ ] Normative graph.
- [ ] Rule execution.
- [ ] Compliance determination.
- [ ] LLM or agent integration.
