# Product specification — Legal Git V1

## 1. Product vision

**Legal Git — Legal data infrastructure for developers.**

Legal Git provides a structured, hierarchical, versioned representation of legal documents through stable identifiers, provenance, diffs, APIs and exports.

The product removes the repeated work of discovering, downloading, parsing, normalizing and maintaining legal corpora independently in every application.

## 2. Primary user

A software developer or technical team building an application that consumes legal texts.

Examples of downstream applications (not built by Legal Git V1):
- legal search and retrieval;
- legal AI agents;
- compliance and regulatory monitoring;
- legal obligation extraction;
- rule engines;
- legal analytics and citation tools.

## 3. Core jobs to be done

A developer should be able to:
- retrieve a legal document and its complete hierarchy;
- retrieve a specific article or structural node directly;
- identify the source and upstream identifier of every item;
- retrieve a specific historical version;
- compare two versions of a node;
- identify which nodes changed between two document snapshots;
- retrieve exact text fragments using offsets scoped to a version;
- download a corpus in a machine-readable format;
- build on the data without writing a bespoke parser for every upstream source.

## 4. V1 functional scope

### 4.1 Source registry
Store:
- source name and publisher;
- jurisdiction;
- source URL or upstream locator, where available;
- source licence metadata, where available;
- retrieval timestamp;
- upstream dataset/package identifier, where available;
- raw source artifact reference, if retained.

### 4.2 Document registry
A document represents the logical legal instrument or text (for example, the Code civil).

Store:
- stable Legal Git ID;
- jurisdiction;
- document type;
- title;
- official/upstream identifier(s);
- publication metadata when available;
- source provenance;
- lifecycle/status metadata when available.

### 4.3 Hierarchical nodes
Represent the structure of a document as nodes:
- part, book, title, chapter, section, subsection;
- article;
- paragraph, alinéa, point or other source-supported subdivision.

The exact node types depend on the source. Do not force every source into a hierarchy it does not provide.

Each node has:
- stable Legal Git ID;
- document ID;
- parent node ID, nullable for root nodes;
- node type;
- source identifier, if available;
- display/order position;
- title/label, if available.

### 4.4 Versioning
Store immutable versions of node content.

Version metadata should support:
- version ID;
- node ID;
- source ID;
- upstream version identifier, if available;
- valid-from / valid-to dates, if provided or reliably derivable from the official source;
- publication/effect dates as separate fields where available;
- ingestion timestamp;
- content format and content hash;
- exact content payload or a reference to it.

Do not collapse publication date, promulgation date, entry-into-force date, and validity period into one generic date.

If a date is unknown, store null and retain the source's original metadata.

### 4.5 Fragments and offsets
V1 supports addressing a fragment of a specific node version.

A fragment is an address into text, not a legal interpretation.

Store or calculate:
- node version ID;
- start offset;
- end offset;
- offset unit (UTF-8 byte, Unicode code point, or another explicitly declared unit);
- content representation identifier/hash.

Offsets must never be reused across versions without revalidation. The same fragment ID may be offered as a persistent reference only when continuity is established; otherwise create a new fragment identity or resolve it through an explicit mapping.

Do not automatically label fragments as “obligation”, “exception”, “condition”, “subject”, or “verb” in V1.

### 4.6 Diffs
Provide:
- version-to-version text diff for a node;
- document-level change listing between two snapshots/versions where supported;
- machine-readable changed ranges;
- links to the old and new version;
- source provenance for both sides.

A diff is a textual/structural change record, not a legal impact assessment.

### 4.7 Developer API
Expose a versioned REST API and OpenAPI contract.

Required capabilities:
- list/search documents using basic metadata filters;
- retrieve a document;
- retrieve its tree/hierarchy;
- retrieve a node;
- list node versions;
- retrieve a particular node version;
- compare two versions;
- retrieve source metadata;
- export/download corpus data.

### 4.8 Bulk export
Support a machine-readable export, at minimum JSONL or JSON. Include stable IDs, hierarchy, version metadata and provenance. Consider NDJSON for streaming.

## 5. V1 non-functional requirements

- Deterministic identifiers.
- Idempotent ingestion.
- Immutable historical versions.
- Traceable provenance.
- Explicit date semantics.
- API pagination.
- Predictable error responses.
- Basic observability for ingestion and API.
- Automated tests and reproducible local development.
- Documentation and sample requests.
- No hidden AI-generated interpretation in canonical records.

## 6. Out of scope

- Legal interpretation or legal advice.
- LLM extraction of legal rules.
- AST generation or syntax annotation.
- Normative/semantic graph.
- Rule execution, compliance decisions or deadline calculations.
- Editorial commentary, doctrine or case-law analysis.
- User-authored amendments to official texts.
- Full-text semantic search or vector database as a V1 dependency.
- Multi-tenant enterprise permissions unless needed for deployment.
- Billing and commercial plan enforcement.

## 7. First release corpus

Recommended pilot: French Code civil.

The ingestion pipeline must:
- identify the exact official dataset/source package;
- preserve raw source provenance;
- map source structure into canonical nodes;
- preserve available historical versions;
- report unsupported or missing structures;
- produce reproducible import results.

Do not claim complete historical coverage unless validated against the source's actual coverage.

## 8. Product success criteria

V1 is useful when an independent developer can:
1. retrieve a Code civil article via API;
2. retrieve its parent hierarchy and source provenance;
3. retrieve at least two historical versions where the source provides them;
4. compare those versions;
5. download a usable corpus export;
6. build a small application without parsing the original source package themselves.

The key validation is external use by developers, not the number of legal features shipped.
