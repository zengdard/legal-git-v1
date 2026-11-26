"""LEGI adapter: maps the DILA LEGI open-data distribution (open licence
v2.0, echanges.dila.gouv.fr/OPENDATA/LEGI) onto canonical entities.

Identity model (source-evidence based, no inference):

- Document identity  : the LEGI texte CID (e.g. LEGITEXT000006070721).
- Section node       : the LEGI section `cid` (stable across section
                       version-fiches: e.g. "Titre III" kept its cid when
                       renamed in 2016). Version fiches of a section record
                       the successive titles in node metadata.
- Article node       : the connected component of article version-fiches
                       joined by their VERSIONS/LIEN_ART lists — the
                       source's own continuity evidence. An article whose
                       numbering moved between sections stays ONE logical
                       node; the placement (parent chain) is recorded per
                       version in version metadata.
- Article version    : one LEGIARTI fiche = one immutable version, with
                       DATE_DEBUT/DATE_FIN valid_from/valid_to as provided
                       by the source (2999-01-01 means "no end" upstream).

Known, documented simplifications:
- Section titles are node metadata (no section-content versions in V1).
- Sens="cible" LIENS are not turned into relationships (the link direction
  is FROM the other texte); they are counted in the report and remain in
  the raw artifact.
- Version placement uses the MOST RECENT fiche of each article for the
  logical parent; placements of historical versions live in version
  metadata.
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.canonical import service as canonical
from app.canonical.models import Node, Relationship
from app.canonical.service import DomainError
from app.core import (
    normalize_slug_component,
    parse_legi_article,
    parse_legi_section,
    parse_legi_struct,
    parse_legi_version,
    sha256_hex,
)
from app.storage import ObjectStore
from app.versioning import service as versioning

REPRESENTATION_XML = "xml-fragment-v1"

LEGI_SOURCE = dict(
    source_id="legi",
    name="LEGI — Légifrance open data (DILA)",
    publisher="Direction de l'information légale et administrative (DILA)",
    jurisdiction="fr",
    source_type="official_dataset",
    base_uri="https://echanges.dila.gouv.fr/OPENDATA/LEGI/",
    licence_name="Licence ouverte v2.0",
    licence_uri="https://www.etalab.gouv.fr/wp-content/uploads/2017/04/ETALAB-Licence-Ouverte-v2.0.pdf",
)

# LICENce ouverte v2.0 attribution: paternité (DILA) + access URL +
# filename and date of the ingested file.
ATTRIBUTION_TEMPLATE = (
    "Données : DILA, base LEGI (licence ouverte v2.0). "
    "Téléchargement : https://echanges.dila.gouv.fr/OPENDATA/LEGI/ — "
    "fichier « {label} »."
)

# LIEN typelien -> canonical relationship type (sens "source" only).
LIEN_TYPE_MAP = {
    "CITATION": "cites",
    "CITATION_TXT": "cites",
    "ABROGATION": "repeals",
    "MODIFICATION": "amends",
    "CODIFICATION": "related_to",
    "CREATION": "related_to",
    "CONCORDANCE": "related_to",
    "TRANSFERT": "related_to",
    "RECTIFICATION": "related_to",
}


@dataclass
class LegiReport:
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
            "liens_sens_cible_skipped": 0,
        }
    )
    errors: list[dict[str, str]] = field(default_factory=list)

    def error(self, where: str, code: str, message: str) -> None:
        self.counts["skipped"] += 1
        self.errors.append({"where": where, "code": code, "message": message})

    def to_dict(self) -> dict[str, Any]:
        return {"counts": dict(self.counts), "errors": list(self.errors)}


def find_texte_root(base: Path, texte_cid: str) -> Path | None:
    """Locates the extracted subtree of one LEGI texte, in a stock or an
    extracted daily directory (any depth)."""
    candidates = [
        p
        for p in sorted(base.rglob(texte_cid))
        if p.is_dir() and (p / "texte" / "struct").is_dir()
    ]
    return candidates[0] if candidates else None


def corpus_manifest(root: Path) -> tuple[str, int]:
    """Deterministic digest of the subtree (sorted relative paths + file
    sha256). Used for run identity/idempotency and the artifact checksum."""
    digest = hashlib.sha256()
    files = sorted(p for p in root.rglob("*.xml") if p.is_file())
    count = 0
    for path in files:
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\x1f")
        digest.update(sha256_hex(path.read_bytes()).encode("ascii"))
        digest.update(b"\x1e")
        count += 1
    return digest.hexdigest(), count


def _pack_tree(root: Path) -> bytes:
    """Deterministic tar.gz of the texte subtree (the retained raw artifact
    for this corpus; the original DILA stock tarball remains the ultimate
    upstream artifact and is referenced in the report)."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            info = tar.gettarinfo(str(path), arcname=path.relative_to(root).as_posix())
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            with path.open("rb") as handle:
                tar.addfile(info, handle)
    return buffer.getvalue()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _as_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _natural_key(num: str | None) -> tuple[int, int]:
    """Natural ordering of article numbers: 1111-1 -> (1111, 1)."""
    if not num:
        return (10**9, 0)
    main, _, suffix = num.partition("-")
    try:
        base = int(main.replace(" ", ""))
    except ValueError:
        return (10**9, 1)
    try:
        sub = int(suffix) if suffix else 0
    except ValueError:
        sub = 0
    if suffix and sub == 0 and not suffix.isdigit():
        sub = 0  # suffixes like "1 A" still order before "2"
    return (base, sub)


def _versions_signature(fiche: dict[str, Any]) -> str:
    ids = sorted(str(v["id"]) for v in fiche["versions"] if v["id"])
    return sha256_hex(json.dumps(ids, ensure_ascii=False))


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, item: str) -> None:
        self.parent.setdefault(item, item)

    def find(self, item: str) -> str:
        self.add(item)
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != root:  # path compression
            self.parent[item], item = root, self.parent[item]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def import_legi_texte(
    session: Session,
    *,
    source_id: str,
    texte_cid: str,
    texte_root: Path,
    release_label: str,
    store: ObjectStore,
    ingestion_run_id: str,
    retrieved_at: datetime | None = None,
) -> dict[str, Any]:
    """Maps one LEGI texte subtree (stock or daily increment) onto canonical
    entities. Runs inside the caller's transaction."""
    report = LegiReport()

    # ------------------------------------------------------------------ struct
    struct_file = texte_root / "texte" / "struct" / f"{texte_cid}.xml"
    if not struct_file.is_file():
        raise DomainError(
            "legi_texte_not_found",
            f"no struct fiche for {texte_cid} under {texte_root}",
        )
    textelr = parse_legi_struct(_read(struct_file))

    version_file = texte_root / "texte" / "version" / f"{texte_cid}.xml"
    titre_court = None
    if version_file.is_file():
        texte_version = parse_legi_version(_read(version_file))
        titre_court = texte_version["titrefull"] or texte_version["titre"]
    title = titre_court or "LEGI texte " + texte_cid

    document, document_created = canonical.get_or_create_document(
        session,
        source_id=source_id,
        jurisdiction=LEGI_SOURCE["jurisdiction"],
        slug=normalize_slug_component(title) or texte_cid.lower(),
        title=title,
        document_type=(textelr["nature"] or "CODE").lower(),
        official_identifier=textelr["cid"] or texte_cid,
        upstream_id=textelr["cid"] or texte_cid,
        meta={
            "upstream_id": textelr["cid"] or texte_cid,
            "ancien_id": textelr["ancien_id"],
            "derniere_modification": textelr["derniere_modification"],
            "base_uri": LEGI_SOURCE["base_uri"],
            "stock_release": release_label,
        },
    )
    report.counts[
        "documents_created" if document_created else "documents_unchanged"
    ] += 1

    # ------------------------------------------------- sections: cid resolution
    section_fiches: dict[str, dict[str, Any]] = {}
    cid_by_fiche: dict[str, str] = {}
    # child order (in-force first) for presentation order of nodes
    order_by_fiche_article: dict[str, int] = {}
    parent_fiche_of_article: dict[str, str] = {}
    order_by_parent_section: dict[tuple[str, str], int] = {}
    parent_fiche_of_section: dict[str, str] = {}

    sections_dir = texte_root / "section_ta"
    section_paths = sorted(sections_dir.rglob("*.xml")) if sections_dir.is_dir() else []
    for path in section_paths:
        fiche = parse_legi_section(_read(path))
        section_fiches[fiche["id"]] = fiche

    def register_listing(parent_fiche_id: str, children: dict[str, Any]) -> None:
        for entry in children["sections"]:
            if entry["id"]:
                cid_by_fiche[entry["id"]] = entry["cid"] or entry["id"]
                parent_fiche_of_section.setdefault(entry["id"], parent_fiche_id)
                order_by_parent_section.setdefault(
                    (parent_fiche_id, entry["cid"] or entry["id"]),
                    int(entry["order"]),
                )
        for entry in children["articles"]:
            if entry["id"]:
                order_by_fiche_article.setdefault(entry["id"], int(entry["order"]))
                parent_fiche_of_article.setdefault(entry["id"], parent_fiche_id)

    for fiche_id, fiche in section_fiches.items():
        register_listing(fiche_id, fiche["children"])
    register_listing(texte_cid, textelr["children"])

    def resolve_cid(fiche_id: str) -> str:
        return cid_by_fiche.get(fiche_id, fiche_id)

    # ---------------------------------------------- sections: canonical nodes
    # BFS from the TEXTELR root listings: parents are always created before
    # children, and the source presentation order (LIEN order) becomes the
    # sibling sort_order directly. Orphan fiches (unlisted) fall back to
    # their TM chain and are reported if their parent cannot be resolved.
    from collections import deque

    section_node_ids: dict[str, str] = {}  # cid -> canonical node id

    def canonical_section_id(cid: str) -> str:
        return canonical.make_node_id(
            document.id, "section", normalize_slug_component(cid)
        )

    root_label_for_cid: dict[str, str] = {}
    for entry in textelr["children"]["sections"]:
        if entry["cid"]:
            root_label_for_cid[entry["cid"] or entry["id"]] = entry["titre"]

    seen_fiches: set[str] = set()
    # (fiche_id, cid, parent_node_id, order, fin, titre)
    queue: deque[tuple[str, str, str | None, int, str | None, str | None]] = deque()
    newest_label: dict[str, tuple[str, str]] = {}  # cid -> (fin, current title)
    for entry in textelr["children"]["sections"]:
        if entry["id"]:
            queue.append(
                (
                    entry["id"],
                    entry["cid"] or entry["id"],
                    None,
                    int(entry["order"]),
                    entry["fin"],
                    entry["titre"],
                )
            )

    def consider_label(cid: str, fin: str | None, titre: str | None) -> None:
        if not titre:
            return
        current = newest_label.get(cid)
        if current is None or (fin or "") > current[0]:
            newest_label[cid] = (fin or "", titre)

    while queue:
        fiche_id, cid, parent_node_id, order, fin, titre = queue.popleft()
        if fiche_id in seen_fiches:
            continue
        seen_fiches.add(fiche_id)
        consider_label(cid, fin, titre)
        fiche = section_fiches.get(fiche_id)
        if fiche is None:
            # Daily increments ship only the fiches that changed; the
            # TEXTELR always lists the full root structure. Absence from an
            # increment is expected, not an anomaly; the node already
            # exists from the stock import.
            report.counts["sections_absent_in_package"] = (
                report.counts.get("sections_absent_in_package", 0) + 1
            )
            continue

        node, created = canonical.get_or_create_node(
            session,
            document_id=document.id,
            node_type="section",
            identifier=cid,
            parent_id=parent_node_id,
            label=root_label_for_cid.get(cid) or fiche["titre_ta"],
            sort_order=order,
            upstream_id=cid,
            meta={"fiche_id": fiche_id},
        )
        section_node_ids[cid] = node.id
        report.counts[
            "sections_created" if created else "sections_unchanged"
        ] += 1

        # Alternative period-fiches of the SAME section share its cid:
        # enqueued siblings are ordered in-force-first so the node label
        # reflects the current title (older fiches then hit the existing
        # node and count as unchanged).
        children_sections = sorted(
            fiche["children"]["sections"],
            key=lambda child: (child["fin"] or "", int(child["order"])),
            reverse=True,
        )
        for child in children_sections:
            if child["id"]:
                queue.append(
                    (
                        child["id"],
                        child["cid"] or child["id"],
                        node.id,
                        int(child["order"]),
                        child["fin"],
                        child["titre"],
                    )
                )

    # Label refresh: each logical section keeps the title of its most
    # recent period fiche (labels are node presentation metadata; version
    # immutability is unaffected).
    for cid, (_fin, titre) in newest_label.items():
        node_id = section_node_ids.get(cid)
        if not node_id:
            continue
        node = session.get(Node, node_id)
        if node is not None and node.label != titre:
            node.label = titre

    # Orphan section fiches: never silently dropped; resolved by their own
    # CONTEXTE chain when the parent is already known.
    def fiche_sort_key(fiche: dict[str, Any]) -> tuple:
        tms = fiche["contexte"]["tms"]
        return (tms[-1]["fin"] if tms else "", fiche["id"] or "")

    for fiche in sorted(section_fiches.values(), key=fiche_sort_key):
        fiche_id = fiche["id"]
        if fiche_id in seen_fiches:
            continue
        seen_fiches.add(fiche_id)
        cid = resolve_cid(fiche_id)
        tms = fiche["contexte"]["tms"]
        parent_cid = resolve_cid(tms[-1]["id"]) if tms else ""
        parent_node_id = section_node_ids.get(parent_cid)
        if not parent_node_id:
            report.error(
                fiche_id,
                "legi_orphan_section",
                f"section fiche {fiche_id} is not listed under a known "
                "parent and its TM chain cannot be resolved; skipped",
            )
            continue
        node, created = canonical.get_or_create_node(
            session,
            document_id=document.id,
            node_type="section",
            identifier=cid,
            parent_id=parent_node_id,
            label=fiche["titre_ta"],
            sort_order=10**9,
            upstream_id=cid,
            meta={"fiche_id": fiche_id},
        )
        section_node_ids[cid] = node.id
        report.counts[
            "sections_created" if created else "sections_unchanged"
        ] += 1

    # ------------------------------------------------ articles: union by sig
    articles_dir = texte_root / "article"
    article_paths = sorted(articles_dir.rglob("*.xml")) if articles_dir.is_dir() else []
    fiches_by_id: dict[str, dict[str, Any]] = {}
    union = _UnionFind()
    groups: dict[str, list[dict[str, Any]]] = {}  # uf root -> fiches

    for path in article_paths:
        fiche = parse_legi_article(_read(path))
        if fiche["id"] is None:
            report.error(str(path), "legi_article_without_id", "fiche without ID")
            continue
        if fiche["contenu"] is None:
            report.error(
                fiche["id"],
                "legi_article_without_content",
                "fiche without BLOC_TEXTUEL/CONTENU is skipped (recorded)",
            )
            continue
        fiches_by_id[fiche["id"]] = fiche
        # Union all versions listed in this fiche: same logical article.
        version_ids = [v["id"] for v in fiche["versions"] if v["id"]]
        if not version_ids:
            # No continuity evidence in the fiche: its own id only.
            union.find(fiche["id"])
            continue
        for vid in version_ids:
            union.union(fiche["id"], vid)

    for fiche_id, fiche in fiches_by_id.items():
        groups.setdefault(union.find(fiche_id), []).append(fiche)

    # ------------------------------------------------- articles: nodes+versions
    for _, group in sorted(groups.items()):
        group.sort(
            key=lambda f: (_as_date(f["date_debut"]) or date.min, f["id"]),
            reverse=True,
        )
        latest = group[0]
        num = latest["num"]
        if not num:
            report.error(latest["id"], "legi_article_without_num", "skipped")
            continue

        tms = latest["contexte"]["tms"]
        parent_cid = resolve_cid(tms[-1]["id"]) if tms else ""
        parent_id = section_node_ids.get(parent_cid)
        if not parent_id:
            report.error(
                latest["id"],
                "legi_article_placement_unresolved",
                f"parent section {parent_cid!r} of article {num} is not "
                "known in this corpus; version fiches kept out until "
                "resolved (raw artifact retains them)",
            )
            continue
        node, created = canonical.get_or_create_node(
            session,
            document_id=document.id,
            node_type="article",
            identifier=num,
            parent_id=parent_id,
            label=f"Article {num}",
            sort_order=order_by_fiche_article.get(
                latest["id"],
                _natural_key(num)[0],
            ),
            upstream_id=f"legi:{texte_cid}:{union.find(latest['id'])}"[:255],
            meta={
                "versions_signature": _versions_signature(latest),
                "legi_version_ids": sorted(
                    str(v["id"]) for v in latest["versions"] if v["id"]
                ),
            },
        )
        if created:
            report.counts["articles_created"] += 1
        else:
            # continuity-conflict check: same num claimed by distinct sources
            # of truth (different version groups reusing the number) is an
            # honest error, never a silent merge.
            existing_sig = node.meta.get("versions_signature")
            if existing_sig and existing_sig != _versions_signature(latest):
                report.error(
                    f"article {num}",
                    "legi_identity_conflict",
                    f"article number {num} reused with a different LEGI "
                    "VERSIONS group; skipped to avoid an unsafe identity merge",
                )
                continue
            report.counts["articles_unchanged"] += 1

        for fiche in group:
            try:
                version, version_created = versioning.create_version(
                    session,
                    node=node,
                    source_id=source_id,
                    ingestion_run_id=ingestion_run_id,
                    content=fiche["contenu"],
                    content_format="xml_fragment",
                    upstream_version_id=fiche["id"],
                    valid_from=_as_date(fiche["date_debut"]),
                    valid_to=_as_date(fiche["date_fin"]),
                    meta={
                        "etat": fiche["etat"],
                        "type": fiche["type"],
                        "origine": fiche["origine"],
                        "contenu_has_markup": fiche["contenu_has_markup"],
                        "tm_chain": [
                            {"id": t["id"], "titre": t["titre"]}
                            for t in fiche["contexte"]["tms"]
                        ],
                        "stock_release": release_label,
                    },
                    representation_id=REPRESENTATION_XML,
                )
            except DomainError as exc:
                # e.g. MODIFIE_MORT_NE fiches have DATE_FIN < DATE_DEBUT in
                # the source; the canonical invariant (valid_to >= valid_from)
                # is kept, the fiche is documented as skipped, never silently
                # normalized. The raw artifact retains it.
                code = (
                    "legi_modifie_mort_ne"
                    if fiche["etat"] == "MODIFIE_MORT_NE"
                    else exc.code
                )
                report.error(
                    fiche["id"],
                    code,
                    f"skipped LEGI fiche ({exc}); source dates "
                    f"{fiche['date_debut']} -> {fiche['date_fin']}",
                )
                continue
            versioning.observe_version(
                session,
                ingestion_run_id=ingestion_run_id,
                version_id=version.id,
            )
            report.counts[
                "versions_created" if version_created else "versions_unchanged"
            ] += 1

            from_node_id = version.node_id
            for lien in fiche["liens"]:
                if lien.get("sens") != "source":
                    report.counts["liens_sens_cible_skipped"] += 1
                    continue
                relationship_type = LIEN_TYPE_MAP.get(
                    str(lien.get("typelien")), "related_to"
                )
                target_id = lien.get("id") or ""
                to_node_id = None
                if target_id in fiches_by_id:
                    target_group = groups.get(union.find(target_id), [])
                    if target_group:
                        target_num = target_group[0]["num"]
                        target_node_id = (
                            canonical.make_node_id(document.id, "article", target_num)
                            if target_num
                            else None
                        )
                        if target_node_id and session.get(Node, target_node_id) is not None:
                            to_node_id = target_node_id
                to_key = to_node_id or f"legi:{target_id or lien.get('titre')}"
                statement = select(Relationship).where(
                    Relationship.from_node_id == from_node_id,
                    Relationship.relationship_type == relationship_type,
                    Relationship.to_key == to_key,
                )
                if session.scalars(statement).first() is not None:
                    report.counts["relationships_unchanged"] += 1
                    continue
                session.add(
                    Relationship(
                        from_node_id=from_node_id,
                        from_document_id=document.id,
                        to_node_id=to_node_id,
                        to_document_id=None,
                        to_key=to_key,
                        relationship_type=relationship_type,
                        source_id=source_id,
                        evidence=lien.get("titre"),
                        meta={
                            "upstream_typelien": lien.get("typelien"),
                            "upstream_sens": lien.get("sens"),
                            "upstream_target_id": target_id or None,
                            "upstream_cidtexte": lien.get("cidtexte"),
                            "upstream_naturetexte": lien.get("naturetexte"),
                        },
                    )
                )
                report.counts["relationships_created"] += 1

    return report.to_dict()
