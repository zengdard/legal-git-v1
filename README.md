# Legal Git v1 — le moteur de documents juridiques versionnés

**Versioned legal-document engine.** Un moteur de données pour vos textes
juridiques — contrats, conditions générales (CGU/CGV), textes réglementaires
— avec des **versions immuables, des diffs exacts et une API REST**.
Conçu pour être auto-hébergé à l'intérieur de vos systèmes : contract
lifecycle, plateforme de T&C, base documentaire de conformité.

> English speakers: Legal Git v1 is a self-hostable engine that stores
> legal texts in a faithful hierarchy, versions them immutably, diffs
> any two versions exactly, and serves everything over a REST API.
> The V2 semantic layer (graph, candidate rules, review workflow) powers
> the hosted edition at https://app.hypetf.com.

## Pourquoi ce moteur

- **Fidélité** : le texte stocké est le texte source, byte-for-byte,
  avec sa provenance complète (hash sha256, identifiants amont, run
  d'ingestion, artefact brut conservé).
- **Immuabilité** : une version d'article ne se modifie jamais — double
  garde ORM + trigger base de données. Les corrections créent une
  nouvelle version, jamais une réécriture silencieuse.
- **Historique exact** : chaque version porte ses dates de validité
  fournies par la source ; les versions s'ordonnent par chronologie
  légale, pas par ordre d'import.
- **Diff vérifiable** : diff caractère-par-caractère (C++), plages en
  points de code Unicode, jamais une interprétation juridique.
- **Hiérarchie fidèle** : livres/titres/chapitres/articles suivis avec
  leur continuité d'identité propre à la source (renommages, renumérotations).
- **API d'abord** : tout est accessible en REST avec contrat OpenAPI
  publié (`docs/spec/openapi.yaml`), fragments par offsets, exports
  NDJSON réimportables.

## Démarrage rapide

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# module natif C++ (diff, parsing, fragments, sha256)
cmake -S core -B core/build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build core/build

# schéma + corpus de démonstration (vrai Code civil, licence ouverte)
.venv/bin/alembic upgrade head
LEGALGIT_DATABASE_URL=sqlite:///var/dev.db .venv/bin/python -m app.ingestion.cli import-fixtures

# API
LEGALGIT_DATABASE_URL=sqlite:///var/dev.db .venv/bin/uvicorn app.main:app --port 8011
```

```bash
curl -s localhost:8011/v1/documents | jq '.items[0]'
curl -s "localhost:8011/v1/nodes/lg:fr:code-civil:article:1103/versions" | jq
```

## Ingestion de vraies sources

Deux adaptateurs officiels sont câblés, avec le même format canonique :

| Source | Contenu | Licence |
|---|---|---|
| **LEGI** (DILA / Légifrance open data) | droit français — ex. le vrai Code civil (6 348 versions datées) | Licence ouverte v2.0 |
| **Legilux** (SCL, Luxembourg) | droit luxembourgeois — actes ELI en Akoma Ntoso | CC BY 4.0 / Licence SCL |

```bash
# LEGI : télécharger le stock, extraire le texte voulu, importer (idempotent)
.venv/bin/python -m app.ingestion.cli import-legi \
    --dir <extrait>/ --texte LEGITEXT000006070721 --release "<fichier>.tar.gz"

# Legilux : un acte par son ELI (négociation de contenu, pas de scraper)
.venv/bin/python -m app.ingestion.cli import-legilux \
    --eli etat/leg/loi/1993/04/05/n1/jo --consolidated
```

Rejouer une ingestion identique ne crée rien (runs idempotents). Les
mentions d'attribution exigées par les licences sont consignées dans
chaque rapport de run.

## Utiliser le moteur pour vos propres documents

Le modèle canonique (Document → Node → NodeVersion → Relationship) est
agnostique : le paquet `app/ingestion/xml_adapter.py` montre la forme
attendue d'un corpus ; un connecteur maison lit votre source et crée
des versions via `app/versioning/service.py::create_version`. Vos
contrats et CGU deviennent des documents versionnés avec diffs, fragments,
arborescence et API — sans jamais écraser l'historique.

## Architecture

- `core/` — cœur C++20 (GoogleTest) : diff LCS plafonné, fragments,
  parsing LEGI, sha256, identifiants déterministes. Lié en Python via
  pybind11.
- `app/` — FastAPI + SQLAlchemy + Alembic : modèle canonique immuable,
  ingestion idempotente, API `/v1`, exports NDJSON, `/metrics` Prometheus.
- `migrations/` — 0001 (schéma) + 0002 (trigger d'immuabilité en base).
- PostgreSQL en production (trigger PL/pgSQL testé), SQLite en dev.

## Garanties testées

- 121 tests C++ (fidélité byte-for-byte sur cas réels, diff 24 cas
  canoniques, reconstruction exacte)
- Suite pytest complète : immuabilité double-garde, historique réel,
  idempotence, contrat OpenAPI servi vs publié, hiémarchie sans cycle,
  reprise après interruption transactionnelle
- CI GitHub Actions : build C++ + pytest + intégration PostgreSQL réelle

## Licence

Apache License 2.0 — voir `LICENSE` et `NOTICE`. Utilisation commerciale
et interne sans condition. Une offre de **licence entreprise**
(support, garantie, indemnisation, modules sémantiques) est décrite dans
`COMMERCIAL.md`.

**Avertissement** : ce moteur est une représentation technique normalisée.
Il ne fournit aucune interprétation juridique ni aucun conseil ; les
publications officielles demeurent seules autoritaires.
