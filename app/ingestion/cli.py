"""Ingestion CLI (internal/admin tooling).

Usage:
    python -m app.ingestion.cli import-fixtures          # demo corpus
    python -m app.ingestion.cli import --source <id> --file <file.xml>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import REPO_ROOT
from app.db.base import Base
from app.db.session import get_engine, get_session_factory
from app.ingestion.service import import_release_bytes
from app.sources.service import get_or_create_source

FIXTURE_DIR = REPO_ROOT / "fixtures" / "code-civil"

# The demo source is explicitly labelled as a fixture: it does not claim to
# be the official Légifrance dataset. Production ingestion must register the
# real source with its real provenance URI (see docs/sources.md).
FIXTURE_SOURCE = {
    "source_id": "fixture-code-civil",
    "name": "Code civil fixture corpus (Legal Git demo)",
    "publisher": "Legal Git development fixture",
    "jurisdiction": "fr",
    "source_type": "official_dataset",
    "base_uri": None,
    "licence_name": None,
    "licence_uri": None,
}


def ensure_schema() -> None:
    # Import every model package so Base.metadata covers all tables
    # before create_all. V2 modules are optional (open-source V1 engine).
    try:
        import app.v2.models  # noqa: F401  (registers V2 tables)
    except ImportError:
        pass

    Base.metadata.create_all(get_engine())


def import_file(source_id: str, path: Path, quiet: bool = False) -> int:
    factory = get_session_factory()
    with factory() as session:
        source, _ = get_or_create_source(session, **_source_params(source_id))
        xml = path.read_bytes()
        run, replayed = import_release_bytes(session, source=source, xml=xml)
        session.commit()
    if not quiet:
        state = "replay (idempotent, nothing created)" if replayed else "imported"
        counts = run.report.get("counts", {})
        print(f"run {run.id}: {state}")
        print(f"  release: {run.upstream_release_id}")
        print(f"  nodes: {counts.get('nodes_created', 0)} created, "
              f"{counts.get('nodes_unchanged', 0)} unchanged")
        print(f"  versions: {counts.get('versions_created', 0)} created, "
              f"{counts.get('versions_unchanged', 0)} unchanged")
        print(f"  raw artifact: {run.raw_artifact_uri}")
        errors = run.report.get("errors", [])
        if errors:
            print(f"  errors: {len(errors)}", file=sys.stderr)
            for error in errors:
                print(f"    - {error['where']}: {error['code']}: {error['message']}",
                      file=sys.stderr)
    return 0


def _source_params(source_id: str) -> dict:
    if source_id == FIXTURE_SOURCE["source_id"]:
        return dict(FIXTURE_SOURCE)
    from app.ingestion.legi_adapter import LEGI_SOURCE
    from app.ingestion.legilux_adapter import LEGILUX_SOURCE

    if source_id == LEGI_SOURCE["source_id"]:
        return dict(LEGI_SOURCE)
    if source_id == LEGILUX_SOURCE["source_id"]:
        return dict(LEGILUX_SOURCE)
    raise SystemExit(
        f"unknown source {source_id!r}; available in V1: "
        f"'{FIXTURE_SOURCE['source_id']}' (demo), the LEGI open data source "
        f"'legi' and the Legilux source 'legilux'."
    )


def import_legi(args: argparse.Namespace) -> int:
    from app.ingestion.legi_service import import_legi_release
    from app.ingestion.xml_adapter import make_store

    base_dir = Path(args.dir).expanduser()
    texte_cid = args.texte

    factory = get_session_factory()
    with factory() as session:
        source, _ = get_or_create_source(session, **_source_params("legi"))
        store = make_store()
        run, replayed = import_legi_release(
            session,
            source=source,
            texte_cid=texte_cid,
            base_dir=base_dir,
            release_label=args.release,
            store=store,
        )
        session.commit()
    counts = run.report.get("counts", {})
    state = "replay (idempotent, nothing created)" if replayed else "imported"
    print(f"run {run.id}: {state}")
    print(f"  texte:  {run.report.get('texte_cid')}")
    print(f"  stock:  {run.report.get('upstream_stock')}")
    print(f"  corpus: {run.report.get('corpus_files')} fiches "
          f"(manifest {run.report.get('corpus_manifest_sha256', '')[:19]}…)")
    print(f"  sections: {counts.get('sections_created', 0)} created, "
          f"{counts.get('sections_unchanged', 0)} unchanged")
    print(f"  articles: {counts.get('articles_created', 0)} created, "
          f"{counts.get('articles_unchanged', 0)} unchanged")
    print(f"  versions: {counts.get('versions_created', 0)} created, "
          f"{counts.get('versions_unchanged', 0)} unchanged")
    print(f"  relationships: {counts.get('relationships_created', 0)} created")
    print(f"  skipped: {counts.get('skipped', 0)} "
          f"(dont liens sens cible: {counts.get('liens_sens_cible_skipped', 0)})")
    print(f"  raw artifact: {run.raw_artifact_uri} "
          f"({run.report.get('raw_artifact_bytes', 0)} octets)")
    errors = run.report.get("errors", [])
    if errors:
        print(f"  erreurs: {len(errors)}", file=sys.stderr)
        for error in errors[:20]:
            print(f"    - {error['where']}: {error['code']}: {error['message']}",
                  file=sys.stderr)
        if len(errors) > 20:
            print(f"    … et {len(errors) - 20} autres", file=sys.stderr)
    return 0


def import_legilux(args: argparse.Namespace) -> int:
    from app.ingestion.legilux_service import import_legilux_release
    from app.ingestion.xml_adapter import make_store

    factory = get_session_factory()
    with factory() as session:
        source, _ = get_or_create_source(session, **_source_params("legilux"))
        store = make_store()
        run, replayed = import_legilux_release(
            session,
            source=source,
            eli_path=args.eli,
            variant="consolidated" if args.consolidated else "original",
            store=store,
            xml_file=args.xml_file,
            turtle_file=args.turtle_file,
            release_label=args.release,
        )
        session.commit()
    counts = run.report.get("counts", {})
    state = "replay (idempotent, nothing created)" if replayed else "imported"
    print(f"run {run.id}: {state}")
    print(f"  ELI:    {run.report.get('eli_path')} ({run.report.get('variant_label')})")
    print(f"  document: {run.report.get('document_id')}")
    print(f"  sections: {counts.get('sections_created', 0)} created, "
          f"{counts.get('sections_unchanged', 0)} unchanged")
    print(f"  articles: {counts.get('articles_created', 0)} created, "
          f"{counts.get('articles_unchanged', 0)} unchanged")
    print(f"  versions: {counts.get('versions_created', 0)} created, "
          f"{counts.get('versions_unchanged', 0)} unchanged")
    print(f"  relationships: {counts.get('relationships_created', 0)} created, "
          f"{counts.get('relationships_unchanged', 0)} unchanged")
    print(f"  licence: {run.report.get('licence')}")
    print(f"  raw artifact: {run.raw_artifact_uri} "
          f"({run.report.get('raw_artifact_bytes', 0)} octets)")
    errors = run.report.get("errors", [])
    if errors:
        print(f"  erreurs: {len(errors)}", file=sys.stderr)
        for error in errors[:20]:
            print(f"    - {error['where']}: {error['code']}: {error['message']}",
                  file=sys.stderr)
        if len(errors) > 20:
            print(f"    … et {len(errors) - 20} autres", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="legal-git-ingest")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("import-fixtures", help="import the demo Code civil corpus")

    single = sub.add_parser("import", help="import one fixture corpus package")
    single.add_argument("--source", required=True)
    single.add_argument("--file", type=Path, required=True)

    legi = sub.add_parser(
        "import-legi", help="import one LEGI texte (DILA open data)"
    )
    legi.add_argument(
        "--dir", type=Path, required=True,
        help="directory containing the extracted LEGI stock or daily tar",
    )
    legi.add_argument(
        "--texte", required=True,
        help="LEGI texte CID, e.g. LEGITEXT000006070721 (Code civil)",
    )
    legi.add_argument(
        "--release", required=True,
        help="label of the ingested stock/daily file (for attribution and "
        "run identity, e.g. Freemium_legi_global_20261108-140000.tar.gz)",
    )

    legilux = sub.add_parser(
        "import-legilux",
        help="import one Legilux act (Journal officiel du Luxembourg)",
    )
    legilux.add_argument(
        "--eli", required=True,
        help="ELI path without base, e.g. etat/leg/loi/1993/04/05/n1/jo",
    )
    legilux.add_argument(
        "--consolidated", action="store_true",
        help="fetch the consolidated text (.../consolide) instead of the "
        "original act",
    )
    legilux.add_argument(
        "--release",
        help="label of the ingested release (default: ELI|variant)",
    )
    legilux.add_argument(
        "--xml-file", type=Path, default=None,
        help="read the Akoma Ntoso XML from a local file instead of HTTP "
        "(tests, offline replays)",
    )
    legilux.add_argument(
        "--turtle-file", type=Path, default=None,
        help="read the RDF (Turtle) metadata from a local file instead of "
        "HTTP",
    )

    args = parser.parse_args(argv)
    ensure_schema()

    if args.command == "import-fixtures":
        files = sorted(FIXTURE_DIR.glob("*.xml"))
        if not files:
            print(f"no fixture files under {FIXTURE_DIR}", file=sys.stderr)
            return 1
        for path in files:
            print(f"== {path.name}")
            import_file(FIXTURE_SOURCE["source_id"], path)
        return 0

    if args.command == "import-legi":
        return import_legi(args)

    if args.command == "import-legilux":
        return import_legilux(args)

    import_file(args.source, args.file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
