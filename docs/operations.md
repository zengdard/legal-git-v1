# Documentation opérationnelle

## Déploiement

Deux modes :

- **Développement / mono-poste** : SQLite + stockage FS + uvicorn (voir
  README). Corpus réel LEGI : `var/legi.db` (API de démonstration sur le
  port 8011).
- **Stack complète** : `podman-compose up --build` — PostgreSQL 16 + API
  (image `Containerfile`, cœur C++ compilé au build, GoogleTests inclus).
  Schéma appliqué par Alembic au démarrage, corpus de démo importé.

Production publique (hors périmètre du pilote V1) : l'image est la même ;
prévoir un frontal (Traefik/Cloudflare), TLS, et les décisions ci-dessous.

## Décisions de sécurité V1 (arrêtées)

| Sujet | Décision du pilote |
|---|---|
| Authentification | API lecture publique sans authentification en V1 pilote (spec API_CONTRACT : « keep API keys/authentication simple for the pilot ») |
| Rate limiting | Non activé pour le pilote ; à brancher (slowapi/nginx) **avant toute exposition publique** |
| Écriture | Aucune : l'ingestion est un outil interne (CLI), l'API est 100 % lecture |
| Limite de taille | Les exports sont calculés à la volée ; le diff est plafonné (16 M cellules, code `diff_too_large`) |
| Immuabilité | Double garde : ORM (`before_update`) + **TRIGGER base de données** (migration 0002) — toute tentative UPDATE/DELETE de `node_versions` est rejetée par le SGBD |

## Surveillance

- `GET /healthz` — liveness ; `GET /readyz` — DB + module natif C++.
- `GET /` — page vitrine (HTML) rendue depuis les **données réelles du
  corpus** (documents, stats, versions de l'article 1103, candidats de
  règles) ; route exclue du contrat OpenAPI (`include_in_schema=False`),
  dégrade proprement sur base vide (fallbacks documentés = vrais textes
  1103).
- Console de consultation (même design, données réelles, lecture seule) :
  `/corpus` (liste des documents avec sources et licences),
  `/corpus/{id}` (arborescence pliable + bandeau d'attribution de licence),
  `/corpus/{id}/a/{n°}` (contenu de la version exacte, timeline des
  versions, sémantique observed_state pour Legilux),
  `/corpus/{id}/a/{n°}/diff?from=&to=` (diff inline `<del>/<ins>` du
  cœur C++), `/licences` (mentions légales exactes LO 2.0 / CC BY 4.0-SCL
  avec date de dernière récupération par source).

## Serveur MCP (agents IA)

`python -m app.mcp_server` (stdio) ou `--http --port 8030` (streamable
HTTP, `/mcp`). 10 outils en lecture seule — documents, articles, versions,
diffs exacts, recherche par identifiant, annotations AST, candidats de
règles, arêtes du graphe — chaque réponse porte le disclaimer de non-
autorité et `legally_validated: null`. Enregistré côté agent (exemple
OpenCode) :

```bash
opencode mcp add legal-git --global --url http://127.0.0.1:8030/mcp
```
- `GET /metrics` — format Prometheus :
  - `legalgit_http_requests_total{method,path,status}` (compteur) ;
  - `legalgit_ingestion_runs`, `legalgit_node_versions`,
    `legalgit_node_version_observations` (jauges rafraîchies au scrape).
- Journaux d'ingestion : `var/legi/daily-update.log` + rapport de chaque run
  en base (`ingestion_runs.report` : comptes, erreurs, éléments non supportés,
  métadonnées de licence/mention).
- Ingestion Legilux (LU) : `import-legilux --eli <ELI> [--consolidated]`
  par acte — pas de cron dédié (pas d'API de veille publique fiable côté
  Legilux ; cf. `docs/legilux-feasibility.md`) ; les événements V2 des
  versions LU sont consommés par le **même worker** que le droit FR.

Exemple de scrape :

```bash
curl -s localhost:8011/metrics | grep legalgit_
```

## Sauvegarde / restauration (testés)

```bash
# Sauvegarde (SQLite : VACUUM INTO ; PostgreSQL : pg_dump via conteneur)
# + tar du stockage objet (artefacts bruts). Checksums dans manifest.txt.
scripts/backup.sh                       # → var/backups/<timestamp>/

# Test de restauration : restaure, démarre l'API sur :8012, vérifie
# /readyz + documents + snapshots, puis nettoie.
scripts/restore_test.sh var/backups/<timestamp>
```

Le test de restauration a été exécuté sur une sauvegarde du corpus LEGI réel
(exit 0 : `/readyz` OK, document `lg:fr:code-civil` lisible, snapshots
préservés). À rejouer après chaque changement de schéma et périodiquement
(cron hebdomadaire recommandé).

## Flotte LEGI : mise à jour quotidienne automatique

Un cron (22h45 Europe/Paris, après la publication DILA ~21h40) exécute
`scripts/daily_legi_update.sh` :

1. lit le répertoire de diffusion DILA et télécharge le dernier
   `LEGI_<stamp>.tar.gz` non déjà téléchargé (débit : ~5–15 Mo/jour) ;
2. l'extrait, détecte si le texte visé (Code civil) a changé ce jour-là ;
3. sinon sortie propre (« rien pour LEGITEXT000006070721 ») ;
4. sinon import idempotent (`import-legi`), log dans
   `var/legi/daily-update.log`.

Le script est sûr à relancer (idempotence par manifest du corpus : un
rejouer ne crée rien). Les jours manqués se rattrapent en important les
incréments manuels manquants — prévoir à terme un rattrapage automatique
de la liste complète.

Ajouter d'autres codes : dupliquer le cron avec
`scripts/daily_legi_update.sh LEGITEXT000006072443` (Code de commerce), etc.

## Base de performances (corpus réel, SQLite mono-poste — 23/11/2026)

Corpus : 4 463 nœuds, 6 348 versions, 14 111 relations (Code civil,
stock 2026-11-08 + incrément 2026-11-20).

| Opération | Latence |
|---|---|
| `GET /v1/documents` | 3,5 ms |
| `GET /v1/documents/{id}/tree` (4 463 nœuds) | 115 ms |
| `GET /v1/nodes/{id}/versions` | 4,3 ms |
| `GET /v1/nodes/{id}/versions/{v}` | 4,1 ms |
| `GET /v1/exports` (manifeste) | 25 ms |
| `GET /v1/exports/{id}` (NDJSON 14,4 Mo) | 1,22 s |
| Import stock complet (7 410 fiches) | 19 s |
| Import incrément quotidien (23 fiches) | < 2 s |

Ces chiffres constituent la référence avant toute optimisation (principe :
mesurer d'abord). Les goulots identifiés si le besoin apparaît : sérialisation
de l'arbre complète par requête (115 ms) et export non streamé — les deux
sont des points d'extension documentés, pas des optimisations à faire
maintenant.

## CI

`.github/workflows/ci.yml` — trois jobs : cœur C++ (CMake + GoogleTests),
application Python (ruff F401, pytest, module pybind11 compilé), build de
l'image conteneur.

## Procédure de restauration en cas d'incident

1. `podman-compose down` (si stack complète) / arrêter uvicorn.
2. Restaurer la dernière sauvegarde : DB dans son emplacement d'origine
   (SQLite : recopier `db.sqlite` ; PG : `psql < db.sql.gz` dans une base
   vierge), stockage via `tar xzf storage.tar.gz`.
3. Relancer l'API ; vérifier `/readyz`, `/metrics` (jauges non nulles),
   une requête métier (`/v1/documents`).
4. `scripts/restore_test.sh <backup>` documente la vérification complète.
