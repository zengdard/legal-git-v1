"""Legilux adapter: maps the Luxembourg Journal officiel (Legilux, Service
central de législation — projet Casemates, http://data.legilux.public.lu)
onto canonical entities. Same canonical format as the French LEGI adapter:
Document / Node / NodeVersion / Relationship, idempotent runs, raw-artifact
retention, no legal interpretation.

Identity model (source-evidence based, no inference):

- Document identity  : the ELI Work URI of the act
                       (e.g. ".../eli/etat/leg/loi/1993/04/05/n1/jo").
                       The document slug is derived from the ELI path
                       (never from the title: titles change between
                       consolidations, ELIs never do).
- Section node       : the Akoma Ntoso container id attribute
                       ("partie_i.chapitre_1"), stable across
                       consolidations of the same act.
- Article node       : the Akoma Ntoso article id attribute
                       ("art_1", "art_1er"). Legilux consolidations do
                       not provide article-level continuity lists like
                       LEGI VERSIONS/LIEN_ART; the AKN id is the source's
                       own continuity evidence.
- Article version    : one observed state of the article content. Unlike
                       LEGI (one fiche = one dated version), Legilux only
                       exposes the CURRENT original or consolidated text:
                       versions here are OBSERVED STATES dated by the act
                       facts (see "version_semantics" in version metadata),
                       never claimed legal validity dates per article.

Known, documented limitations (kept honest, never silently normalized):
- Article versions carry the ACT's dateEntryInForce as valid_from basis
  (no article-level dates exist in Legilux); the basis is recorded in
  version metadata as "date_basis".
- An act modified in place upstream produces a new observed version on the
  next import (content fingerprint); no upstream version id exists.
- inForceStatus comes from the RDF (Turtle) resource, parsed defensively;
  absence is recorded as None, never guessed.

Relations: the JOLUX act-level predicates (cites, modifies, repeals,
transposes) become document-level canonical Relationships (from_node_id is
NULL, from_document_id set) with the ELI target as to_key and resolution
against already-imported Legilux documents. Same-document or cross-document
node-level relations are NOT inferred (no legal interpretation).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.canonical import service as canonical
from app.canonical.models import Document, Relationship
from app.canonical.service import DomainError
from app.versioning import service as versioning

try:  # V2 graph sync is optional (open-source V1 engine)
    from app.v2.models import GraphEdge
except ImportError:  # pragma: no cover - exercised in the V1 dist builds
    GraphEdge = None

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0/CSD13"
SCL_NS = "http://www.scl.lu"
AKN = f"{{{AKN_NS}}}"
SCL = f"{{{SCL_NS}}}"
REPRESENTATION_XML = "xml-fragment-v1"

LEGILUX_BASE = "http://data.legilux.public.lu"

LEGILUX_SOURCE = dict(
    source_id="legilux",
    name="Legilux — Journal officiel du Grand-Duché de Luxembourg (Casemates)",
    publisher="Ministère d'État — Service central de législation (SCL)",
    jurisdiction="lu",
    source_type="official_dataset",
    base_uri="https://legilux.public.lu/",
    licence_name="Creative Commons Attribution 4.0",
    licence_uri="https://creativecommons.org/licenses/by/4.0/",
)

# Licence SCL for consolidated texts (re-use licence of the SCL); the
# dataset-level licence remains CC BY 4.0 (data.public.lu).
ATTRIBUTION_TEMPLATE = (
    "Données : Ministère d'État — Service central de législation, Legilux "
    "(CC BY 4.0 / Licence de réutilisation SCL pour les textes consolidés). "
    "Téléchargement : http://data.legilux.public.lu{eli_path} — "
    "variante « {variant} »."
)

AUTHORITY_NOTE = (
    "Legilux (https://legilux.public.lu) demeure la source authentique de "
    "publication ; ces données en sont une représentation technique "
    "normalisée. Seuls les textes publiés au Journal officiel du "
    "Grand-Duché de Luxembourg font foi."
)

# JOLUX act-level predicate -> canonical relationship type. "transposes"
# maps to "implements" (vocabulary shared with the V2 graph edge types).
JOLUX_PREDICATE_MAP = {
    "cites": "cites",
    "modifies": "amends",
    "repeals": "repeals",
    "transposes": "implements",
}

CONTAINERS = ("part", "title", "chapter", "section", "subchapter")


@dataclass
class LegiluxReport:
    counts: dict[str, int] = field(
        default_factory=lambda: {
            "documents_created": 0,
            "documents_unchanged": 0,
            "sections_created": 0,
            "sections_unchanged": 0,
            "articles_created": 0,
            "articles_unchanged": 0,
            "versions_created": 0,
            "versions_unchanged": 0,
            "relationships_created": 0,
            "relationships_unchanged": 0,
            "skipped": 0,
        }
    )
    errors: list[dict[str, str]] = field(default_factory=list)

    def error(self, where: str, code: str, message: str) -> None:
        self.counts["skipped"] += 1
        self.errors.append({"where": where, "code": code, "message": message})

    def to_dict(self) -> dict[str, Any]:
        return {"counts": dict(self.counts), "errors": list(self.errors)}


# --------------------------------------------------------------------------
# Akoma Ntoso parsing (pure stdlib; the C++ core keeps LEGI-specific parsers,
# Legilux Akoma Ntoso is parsed here with the stdlib ElementTree).
# --------------------------------------------------------------------------


def _text_of(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _serialize_inline(element: ET.Element) -> str:
    """Deterministic XML fragment of one Akoma Ntoso element, local tag
    names only, namespace declarations stripped (same convention as the
    LEGI xml_fragment content format)."""
    parts = [f"<{_local(element.tag)}"]
    for key in sorted(element.attrib):
        if key.startswith("{"):
            continue  # scl presentation attributes are not canonical content
        parts.append(f' {key}="{element.attrib[key]}"')
    parts.append(">")
    if element.text and element.text.strip():
        parts.append(element.text.strip())
    for child in element:
        parts.append(_serialize_inline(child))
        if child.tail and child.tail.strip():
            parts.append(child.tail.strip())
    parts.append(f"</{_local(element.tag)}>")
    return "".join(parts)


def _article_content_fragment(article: ET.Element) -> str:
    """The article content as an XML fragment: every block-level element
    found inside the article's alinea/paragraph content containers, in
    source order, one per line. Nothing is invented or reformatted."""
    blocks: list[str] = []
    for element in article.iter():
        if _local(element.tag) != "content":
            continue
        for child in element:
            blocks.append(_serialize_inline(child))
    return "\n".join(blocks)


def _article_number(article: ET.Element) -> str:
    raw = _text_of(article.find(f"{AKN}num"))  # "Art. 1er." / "Art. 34."
    number = re.sub(r"^art\.?", "", raw.strip(), flags=re.IGNORECASE).strip()
    return number.rstrip(".").strip()


def _natural_order(number: str) -> tuple[int, int, str]:
    match = re.match(r"(\d+)\s*([a-z]*)", number)
    if match is None:
        return (10**9, 0, number)
    base = int(match.group(1))
    suffix = match.group(2)
    return (base, 0 if suffix in ("er", "") else 1, number)


def parse_in_force_status(turtle: str | None) -> str | None:
    """Defensive extraction of jolux:inForceStatus from the RDF Turtle
    dump of the same resource. Resolves @prefix declarations so the value
    is the full URI's last segment (e.g. 'in-force'); absence → None."""
    if not turtle:
        return None
    prefixes: dict[str, str] = {}
    for line in turtle.splitlines():
        match = re.match(r"\s*@prefix\s+([a-zA-Z0-9_-]*)\s*:\s*<([^>]+)>", line)
        if match:
            prefixes[match.group(1)] = match.group(2)
    for line in turtle.splitlines():
        match = re.search(r"jolux:inForceStatus\s+(\S+)\s*[;,.]?", line)
        if match:
            value = match.group(1).rstrip(";,. ")
            if value.startswith("http"):
                return value.rstrip("/").rsplit("/", 1)[-1]
            head, _, local = value.partition(":")
            base = prefixes.get(head, "")
            resolved = base + local
            return local if not base else resolved.rstrip("/").rsplit("/", 1)[-1]
    return None


def parse_akn_act(xml_text: str) -> dict[str, Any]:
    """Parses one Legilux Akoma Ntoso act (original or consolidated
    variant) into a structured dict. Raises DomainError on structural
    problems (never silently degrades)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise DomainError("legilux_parse_error", f"invalid Akoma Ntoso XML: {exc}")
    act = root.find(f"{AKN}act")
    if act is None:
        raise DomainError(
            "legilux_not_an_act",
            "the resource is not an Akoma Ntoso <act> (treaties and other "
            "types are not supported by this adapter in V1)",
        )

    identification = act.find(f"{AKN}meta/{AKN}identification")
    frbr_work = identification.find(f"{AKN}FRBRWork") if identification is not None else None
    eli = (frbr_work.find(f"{AKN}FRBRthis").get("value") or "") if frbr_work is not None else ""
    if not eli:
        raise DomainError(
            "legilux_missing_eli", "FRBRWork/FRBRthis carries no ELI value"
        )

    # JOLUX facts (title, dates, act-level relations) by scl:name.
    # The <jolux> fact elements live in the scl namespace, not the AKN one.
    facts: dict[str, list[str]] = {}
    for element in act.iter():
        if element.tag != f"{SCL}jolux":
            continue
        name = element.get(f"{SCL}name")
        value = (element.text or "").strip()
        if name and value and value not in facts.get(name, []):
            facts.setdefault(name, []).append(value)

    title = (facts.get("title") or [""])[0]
    if not title:
        preface = act.find(f"{AKN}preface/{AKN}longTitle")
        title = _text_of(preface) or eli.rsplit("/", 1)[-1]
    # Presentation cleanup only: the JOLUX title fact sometimes carries
    # literal "\n" sequences (JSON-escaped upstream, e.g. "...portant\n1.
    # approbation...") and raw line breaks; canonical titles are
    # single-spaced. Content versions are never touched.
    title = " ".join(
        title.replace("\\n", " ").replace("\\t", " ").split()
    )

    # Hierarchy: container elements (part/title/chapter/...) in document
    # order, then articles keyed by their Akoma Ntoso id.
    body = act.find(f"{AKN}body")
    if body is None:
        raise DomainError("legilux_no_body", "act has no <body>")

    sections: list[dict[str, Any]] = []  # flat, in document order
    articles: list[dict[str, Any]] = []

    def walk(element: ET.Element, parent_id: str | None, order_offset: int) -> int:
        count = 0
        for child in element:
            tag = _local(child.tag)
            if tag in CONTAINERS:
                identifier = child.get("id") or f"{parent_id or 'root'}_{len(sections) + 1}"
                label = _text_of(child.find(f"{AKN}heading")) or _text_of(child.find(f"{AKN}num")) or identifier
                sections.append(
                    {
                        "id": identifier,
                        "parent_id": parent_id,
                        "label": label,
                        "kind": tag,
                        "sort_order": order_offset + count,
                    }
                )
                count += 1
                count += walk(child, identifier, count)
            elif tag == "article":
                identifier = child.get("id")
                if not identifier:
                    raise DomainError(
                        "legilux_article_without_id",
                        f"<article> without id attribute near '{_text_of(child)[:40]}'",
                    )
                content = _article_content_fragment(child)
                if not content:
                    raise DomainError(
                        "legilux_article_without_content",
                        f"article {identifier} has no content container",
                    )
                articles.append(
                    {
                        "id": identifier,
                        "number": _article_number(child),
                        "heading": _text_of(child.find(f"{AKN}heading")),
                        "parent_id": parent_id,
                        "content": content,
                        "sort_order": order_offset + count,
                    }
                )
                count += 1
        return count

    walk(body, None, 0)

    # Attachments (annexes, <attachments><attachment><doc>): structured
    # sub-documents of the act. V1 does not import them as canonical
    # nodes (their article numbering is per-document and would collide
    # with the act's own articles); they are counted, listed and kept in
    # the raw artifact — never silently dropped.
    attachments: list[dict[str, Any]] = []
    attachment_articles = 0
    attachments_element = act.find(f"{AKN}attachments")
    if attachments_element is not None:
        for attachment in attachments_element:
            doc = attachment.find(f"{AKN}doc")
            if doc is None:
                continue
            heading = _text_of(doc.find(f"{AKN}preface/{AKN}longTitle"))[:200]
            articles_inside = sum(
                1 for element in doc.iter() if _local(element.tag) == "article"
            )
            attachment_articles += articles_inside
            attachments.append({"heading": heading, "articles": articles_inside})

    return {
        "eli": eli,
        "title": title,
        "date_document": (facts.get("dateDocument") or [None])[0],
        "publication_date": (facts.get("publicationDate") or [None])[0],
        "date_entry_in_force": (facts.get("dateEntryInForce") or [None])[0],
        "historical_legal_id": (facts.get("historicalLegalId") or [None])[0],
        "is_part_of": (facts.get("isPartOf") or [None])[0],
        "relations": {
            predicate: facts.get(predicate, [])
            for predicate in JOLUX_PREDICATE_MAP
        },
        "sections": sections,
        "articles": articles,
        "attachments": attachments,
        "attachment_articles": attachment_articles,
    }


# --------------------------------------------------------------------------
# Canonical import
# --------------------------------------------------------------------------


def _as_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _eli_path_parts(eli: str) -> list[str]:
    """eli/etat/leg/loi/1993/04/05/n1/jo -> [loi, 1993, 04, 05, n1, jo]
    (base/eli/etat/{leg|adm} prefixes are stripped; what identifies the
    act to a human reader is the type + date + number)."""
    path = eli.replace("http://data.legilux.public.lu/", "").strip("/")
    parts = [part for part in path.split("/") if part]
    while parts and parts[0] in ("eli", "etat", "leg", "adm"):
        parts.pop(0)
    if len(parts) < 2:
        raise DomainError(
            "legilux_bad_eli", f"cannot derive a document slug from ELI {eli!r}"
        )
    return parts


def _document_slug(eli: str) -> str:
    """Deterministic slug from the ELI path (the title is never used:
    titles change across consolidations, ELIs never do)."""
    return "-".join(_eli_path_parts(eli))


def _resolve_target_eli(session: Session, target: str) -> dict[str, Any]:
    """Resolves one relation target ELI (e.g. '/eli/etat/leg/loi/2002/12/
    20/n8/jo') to a to_key and, when the target act is already imported,
    to its canonical document id. The to_key is always the full ELI URI
    prefixed with 'legilux:' (or 'eli:' for non-état targets such as EU
    directives): one stable shape, resolved or not."""
    path = target.strip().lstrip("/")
    absolute = f"{LEGILUX_BASE}/{path}"
    statement = select(Document).where(
        Document.official_identifier == absolute
    )
    document = session.scalars(statement).first()
    if document is not None:
        return {
            "to_key": f"legilux:{document.official_identifier}",
            "to_document_id": document.id,
        }
    if path.startswith("eli/etat/"):
        return {"to_key": f"legilux:{absolute}", "to_document_id": None}
    if path.startswith("eli/"):
        path = path.removeprefix("eli/")
    return {"to_key": f"eli:{LEGILUX_BASE}/eli/{path}", "to_document_id": None}


def relink_legilux_references(session: Session) -> int:
    """Links relationships whose to_key is a Legilux ELI to the canonical
    document id of that act, once it has been imported. Pure identifier
    mapping (to_key ↔ official_identifier), no content or semantic
    inference. Idempotent; runs after every Legilux run, replay included.

    Any V2 graph edge previously backfilled from the relationship follows
    the resolution (resolution bookkeeping only — the relation itself,
    its origin and evidence never change)."""
    resolved = 0
    statement = select(Relationship).where(
        Relationship.to_key.like("legilux:%"),
        Relationship.to_document_id.is_(None),
    )
    for relationship in session.scalars(statement):
        identifier = relationship.to_key.removeprefix("legilux:")
        document = session.scalars(
            select(Document).where(Document.official_identifier == identifier)
        ).first()
        if document is None:
            continue
        relationship.to_document_id = document.id
        resolved += 1
        if GraphEdge is None:
            continue  # V1 engine: no graph edges to follow the resolution
        for edge in session.scalars(
            select(GraphEdge).where(
                GraphEdge.origin == "official_metadata",
                GraphEdge.from_entity_type == "document",
                GraphEdge.from_entity_id == relationship.from_document_id,
                GraphEdge.relation_type == relationship.relationship_type,
                GraphEdge.to_entity_id.is_(None),
            )
        ):
            if (edge.metadata_json or {}).get("v1_relationship_id") != relationship.id:
                continue  # another unresolved edge of the same type
            edge.to_entity_id = document.id
            edge.to_entity_type = "document"
            edge.resolution_status = "resolved"
    return resolved


def import_legilux_act(
    session: Session,
    *,
    source_id: str,
    xml_text: str,
    turtle_text: str | None,
    variant: str,
    ingestion_run_id: str,
    release_label: str,
) -> tuple[str, dict[str, Any]]:
    """Maps one Legilux act (one observed variant: 'original' or
    'consolidated') onto canonical entities. Runs inside the caller's
    transaction. Returns (document_id, report)."""
    if variant not in ("original", "consolidated"):
        raise DomainError("legilux_bad_variant", f"unknown variant {variant!r}")

    report = LegiluxReport()
    parsed = parse_akn_act(xml_text)
    eli = parsed["eli"]
    in_force_status = parse_in_force_status(turtle_text)
    if parsed["attachments"]:
        # Not an error: annexes are legitimately retained in the raw
        # artifact but not mapped in V1 (documented limitation).
        report.counts["attachments_skipped"] = len(parsed["attachments"])
        report.counts["attachment_articles_skipped"] = parsed["attachment_articles"]

    slug = _document_slug(eli)
    document_type = _eli_path_parts(eli)[0]
    document, document_created = canonical.get_or_create_document(
        session,
        source_id=source_id,
        jurisdiction=LEGILUX_SOURCE["jurisdiction"],
        slug=slug,
        title=parsed["title"],
        document_type=document_type,
        official_identifier=eli,
        upstream_id=eli,
        meta={
            "eli": eli,
            "date_document": parsed["date_document"],
            "publication_date": parsed["publication_date"],
            "date_entry_in_force": parsed["date_entry_in_force"],
            "historical_legal_id": parsed["historical_legal_id"],
            "is_part_of": parsed["is_part_of"],
            "in_force_status": in_force_status,
            "data_license": LEGILUX_SOURCE["licence_name"],
            "consolidated_license": "Licence de réutilisation SCL",
            "authority_note": AUTHORITY_NOTE,
        },
    )
    if not document_created:
        # Additive meta only: facts not yet recorded are filled in, no
        # recorded fact is ever rewritten (the first observation stands).
        merged = dict(document.meta or {})
        for key, value in (
            ("in_force_status", in_force_status),
            ("date_entry_in_force", parsed["date_entry_in_force"]),
            ("historical_legal_id", parsed["historical_legal_id"]),
        ):
            if not merged.get(key) and value:
                merged[key] = value
        variants = dict(merged.get("observed_variants") or {})
        variants.setdefault(variant, release_label)
        merged["observed_variants"] = variants
        document.meta = merged
    else:
        document.meta = {
            **document.meta,
            "observed_variants": {variant: release_label},
        }
    report.counts[
        "documents_created" if document_created else "documents_unchanged"
    ] += 1

    # ------------------------------------------------------------- sections
    section_node_ids: dict[str, str] = {}
    for section in parsed["sections"]:
        node, created = canonical.get_or_create_node(
            session,
            document_id=document.id,
            node_type="section",
            identifier=section["id"],
            parent_id=section_node_ids.get(section["parent_id"]),
            label=section["label"],
            sort_order=section["sort_order"],
            upstream_id=f"{eli}#{section['id']}",
            meta={"kind": section["kind"]},
        )
        section_node_ids[section["id"]] = node.id
        report.counts[
            "sections_created" if created else "sections_unchanged"
        ] += 1

    # ------------------------------------------- articles: nodes + versions
    for article in parsed["articles"]:
        node, created = canonical.get_or_create_node(
            session,
            document_id=document.id,
            node_type="article",
            identifier=article["number"],
            parent_id=section_node_ids.get(article["parent_id"]),
            label=f"Article {article['number']}"
            if not article["heading"]
            else f"Article {article['number']} — {article['heading']}",
            sort_order=_natural_order(article["number"])[0],
            upstream_id=f"{eli}#{article['id']}",
            meta={"akn_id": article["id"], "heading": article["heading"]},
        )
        report.counts[
            "articles_created" if created else "articles_unchanged"
        ] += 1

        version, version_created = versioning.create_version(
            session,
            node=node,
            source_id=source_id,
            ingestion_run_id=ingestion_run_id,
            content=article["content"],
            content_format="xml_fragment",
            upstream_version_id=f"{eli}/fr@{variant}",
            valid_from=_as_date(parsed["date_entry_in_force"]),
            valid_to=None,
            meta={
                # Observed-state semantics: honest about what Legilux
                # provides (no per-article legal validity dates).
                "version_semantics": "observed_state",
                "variant": variant,
                "akn_id": article["id"],
                "eli": eli,
                "language": "fr",
                "date_basis": "act_date_entry_in_force",
                "release_label": release_label,
                "text_source": "i.e. Legilux (SCL), CC BY 4.0 / licence SCL",
            },
            representation_id=REPRESENTATION_XML,
        )
        versioning.observe_version(
            session,
            ingestion_run_id=ingestion_run_id,
            version_id=version.id,
        )
        report.counts[
            "versions_created" if version_created else "versions_unchanged"
        ] += 1

    # ----------------------------------------- act-level JOLUX relations
    dedupe: dict[tuple[str], bool] = {}
    for predicate, targets in parsed["relations"].items():
        relationship_type = JOLUX_PREDICATE_MAP[predicate]
        for target in targets:
            resolved = _resolve_target_eli(session, target)
            key = (relationship_type, resolved["to_key"])
            if dedupe.get(key):
                continue
            statement = select(Relationship).where(
                Relationship.from_document_id == document.id,
                Relationship.from_node_id.is_(None),
                Relationship.relationship_type == relationship_type,
                Relationship.to_key == resolved["to_key"],
            )
            if session.scalars(statement).first() is not None:
                dedupe[key] = True
                report.counts["relationships_unchanged"] += 1
                continue
            session.add(
                Relationship(
                    from_node_id=None,
                    from_document_id=document.id,
                    to_node_id=None,
                    to_document_id=resolved["to_document_id"],
                    to_key=resolved["to_key"],
                    relationship_type=relationship_type,
                    source_id=source_id,
                    evidence=target,
                    meta={
                        "upstream_predicate": predicate,
                        "origin": "jolux_act_metadata",
                        "target_eli": target,
                    },
                )
            )
            dedupe[key] = True
            report.counts["relationships_created"] += 1

    return document.id, report.to_dict()
