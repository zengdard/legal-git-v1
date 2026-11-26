# Infrastructure de tests

La propriété fondamentale testée partout :

> Un développeur doit pouvoir faire confiance à Legal Git pour retrouver le
> bon texte, dans la bonne version, au bon endroit, avec une provenance
> vérifiable et un historique exact.

Le tout est automatisé en CI (`.github/workflows/ci.yml`), merge bloquant
sur échec. Exécution locale :

```bash
./core/build/core_tests   # C++ (GoogleTest)
.venv/bin/python -m pytest                  # toute la suite Python
.venv/bin/python -m pytest -m benchmark -s   # mesures de performance
LEGALGIT_PG_URL=postgresql+pg8000://… .venv/bin/python -m pytest tests/integration/test_pg_integration.py
```

## Cartographie des 8 catégories

| # | Catégorie | Où | Volume |
|---|---|---|---|
| 1 | Fonctionnel P0 (sources → API) | `tests/integration/test_api.py`, `test_versions.py`, `test_hierarchy.py`, `test_ingestion.py` | 25 tests |
| 2 | Fidélité du texte | `core/tests/test_fidelity.cpp` (24 cas canoniques + reconstruction byte-for-byte sur CHAQUE cas) + `tests/integration/test_fidelity.py` (restitution pipeline complet contre le parsing C++ des vraies fiches) | 25 |
| 3 | Identité et hiérarchie | `test_fidelity.py` (identité stable malgré changement de contenu, titres, numéros identiques entre documents, nœud retiré = historique conservé, renumérotation ≠ fusion silencieuse) + `test_hierarchy.py` | 12 |
| 4 | Versioning et historique | `test_versions.py` (immuabilité double-garde, dates jamais confondues,pas d'historique inventé) + ordre chronologique `valid_from asc nulls last` | 13 |
| 5 | Fragments et offsets | `test_fragments_api.py` : début/fin/vide, offsets négatifs et hors bornes rejetés, accents et multibytes = 1 point de code, fragments d'anciennes versions accessibles, offsets V1 jamais réutilisés sur V2, représentation exacte requise | 15 |
| 6 | Ingestion des sources | `test_ingestion_robustness.py` : XML malformé, racine invalide, encodage incorrect, doublons amont, métadonnées absentes = null, **interruption à mi-import = transaction tout-ou-rien + reprise propre + replay idempotent**, 2 releases ≠ | 7 |
| 7 | API et intégration | `test_contract.py` (contrat `docs/spec/openapi.yaml` vs surface réellement servie via `/openapi.json`, forme d'erreur contractuelle, pagination complète sur 250 documents sans doublon ni perte) + `test_pg_integration.py` (PostgreSQL réel : TRIGGER PL/pgSQL, JSONB, import complet) | 8 |
| 8 | Performance et robustesse | `tests/perf/test_benchmarks.py` (marqueur `benchmark`) : hash Mo/s, diff ms/paire d'articles réels, parsing µs/fiche DILA, arbre 1 000 nœuds, débit export | 5 |

Plus les suites existantes : core bridge (checksums croisés hashlib, diff,
fragments), LEGI adapter (`test_legi_adapter.py`, **fiches DILA réelles** :
provenance/licence/mention, continuité VERSIONS malgré renommage de section,
idempotence, arborescence réelle), **Legilux adapter**
(`test_legilux_adapter.py`, **actes luxembourgeois réels** : ELI→Document,
hierarchie parties/chapitres, versions = états observés, relations JOLUX
niveau acte avec re-résolution croisée, annexes comptées, V2 sur langue
française) et le **test en or**.

## Le test en or

`tests/integration/test_golden_e2e.py` — le scénario critique imposé par la
spécification : un article réel du Code civil (1103), ses deux versions
historiques réelles (1804-03-21 → 2016-10-01 « MODIFIE » avec contenu
XHTML, 2016-10-01 → « VIGUEUR »), exactitude byte-for-byte (espace final
inclus, hash sha256), diff réel avec plages vérifiées par découpe, fragment
précis localisé **dans chaque version**, non-réutilisation des offsets
entre versions, placement hiérarchique exact (Livre III → Titre III →
Chapitre Ier « Dispositions liminaires », cid stable à travers le
renommage 2016), et historique complet reconstruit depuis l'export NDJSON
avec checksum.

## Découvertes faites par les tests (à conserver)

- Le diff sur textes répétitifs peut ancrer un bloc à une position
  équivalente (alignement minimal ambigu) — la reconstruction exacte reste
  la propriété contractuelle ; les offsets absolus ne sont garantis que sur
  contenu non ambigu (documenté dans `docs/diff.md`).
- `fastapi >= 0.165` monte les routers en différé (`_IncludedRouter`) : la
  surface servie se vérifie via `/openapi.json`, pas `app.routes`.
- L'ordre des versions suit désormais la chronologie légale
  (`valid_from asc nulls last`), pas l'ordre d'ingestion.

## Checklist de validation V1 (mesurée)

| Critère | Résultat |
|---|---|
| Fidélité : fixtures de référence restituées sans modification | ✅ byte-for-byte (C++ fidélité + restitution pipeline, fiches DILA réelles) |
| Versioning : aucune ancienne version écrasée | ✅ double garde ORM + TRIGGER SQL (SQLite et PostgreSQL réels testés) |
| Identifiants : aucun doublon au réimport | ✅ replay idempotent, même run id |
| Hiérarchie : aucun cycle ni parent invalide | ✅ cycles rejetés, parents inter-documents rejetés |
| Diff : 100 % des modifications attendues détectées | ✅ 24 cas canoniques + reconstruction exacte sur chacun |
| Fragments : tout offset valide restitue le bon contenu | ✅ 15 tests API, unités = points de code |
| Provenance : chaque version traçable | ✅ source + run + artefact brut + release amont + mention DILA |
| Ingestion : reprise après interruption sans corruption | ✅ transaction tout-ou-rien prouvée (panne simulée à ~66 %) |
| API : tous les endpoints documentés testés | ✅ 101 tests + contrat openapi.yaml |
| Export : réimportable et cohérent avec la base | ✅ checksum vérifié, ids stables, contenu exact |

# Tests V2 (couche sémantique)

| Suite | Portée |
|-------|--------|
| `core/tests/test_v2_semantic.cpp` (15) | extraction de références (articles, numéros L./R./D., ids LEGI) + analyse syntaxique (phrases, conditions, exceptions, deontic cues obligation/prohibition/permission, candidats sujet/action, spans valides) |
| `tests/integration/test_v2_graph.py` (7) | résolution (résolu/non résolu), idempotence, non-promotion `cites` → `amends`, backfill V1 (origin `official_metadata`), traversée bornée |
| `tests/integration/test_v2_pipeline.py` (7) | outbox transactionnel, spans validés (§9), candidats avec evidence, jamais d'écrasement de revue, impacts + déduplication, fragments exacts, **paire > plafond diff ne bloque pas la file** |
| `tests/integration/test_v2_api.py` (11) | auth (401/403/422/409), idempotence des runs, provenance dans les réponses, workflow de revue audité, endpoints impacts, schéma JSON publié, absence de toute conclusion de conformité |
| `tests/unit/test_v2_logging.py` (2) | rotation intégrée : `RotatingFileHandler` pour le worker, `rotate_if_needed` pour les logs shell |
| `tests/integration/test_legilux_adapter.py` (16) | adaptateur Legilux sur **actes réels LU** : ELI→Document, hiérarchie parties/chapitres, versions = états observés (`xml-fragment-v1`), relations JOLUX niveau document + re-résolution croisée, annexes comptées, V2 (AST) sur langue française sans adaptation |

## Checklist de validation V2 (mesurée)

| Critère (spec V2, §9 release gates) | Résultat |
|---|---|
| Provenance de la source préservée de bout en bout | ✅ chaque règle/impact/edge référence un `node_version_id` + span + pipeline |
| Distinction citations vs effets légaux | ✅ `relation_type` et `origin` explicites ; test de non-promotion |
| Annotations version-scopées et span-addressables | ✅ `representation_id` + code points + validation span (§9) |
| Candidats revueillables, jamais auto-validés | ✅ `automatically_extracted=true`, `legally_validated=null`, `review_status` workflow audité |
| Changements de source → impacts explicables | ✅ mapping `mapped/ambiguous/whole_node` + `reason_code` + ranges |
| Consommateurs API distinguent machine / source-backed / humain | ✅ champs `origin` (4 classes), review identity persistée dans table distincte |

## Découvertes faites par les tests V2 (à conserver)

- `_previous_version` doit recourir en dernier recours à `ingested_at`
  (chronologie d'ingestion) car certaines versions historiques n'ont pas de
  `valid_from` (fixture sans dates) — le résolveur
  `valid_from asc nulls_last, ingested_at, id` couvre les deux cas.
- Le diff C++ est ambigu sur textes répétitifs : l'ancrage des blocs peut
  se déplacer vers une position équivalente (à distance égale) — le moteur
  d'impact marque ces dépendances `whole_node` pour ne jamais deviner.
- pydantic-settings lit `LEGALGIT_V2_API_KEYS` au premier import de
  `app.config` : en tests, l'`env` doit être posée dans `conftest.py`
  avant tout import applicatif (contrat déjà respecté par les fixtures).
- **Paire de versions au-dessus du plafond de diff** (découvert sur le
  backlog réel du Code civil : 3540 + 5391 points de code ≈ 19 M cellules
  LCS > plafond 16 M) : le `CoreError` du binding échappait au
  `except DomainError` du moteur d'impact et **bloquait toute la file
  worker**. Corrigé : la paire est skippée et comptée
  (`impact_diff_unavailable`), l'événement est marqué traité ; test de
  non-régression dans `test_v2_pipeline.py`
  (`test_worker_survives_oversized_version_pair`).
- Les modèles V2 doivent être importés **avant** `create_all` : le
  `conftest.py` importe `app.v2.models` explicitement, sinon l'exécution
  d'un fichier de tests isolé échoue (`no such table: source_events`).



## Ce qui n'est PAS testé (par délimitation V1/V2)

Justesse d'un AST juridique, extraction d'obligations, interprétation
d'exceptions, pertinence de règles, conformité d'entreprise, qualité de
réponses d'agents IA — ces tests appartiennent aux futurs modules Legal
Parsing / Legal Rules.
