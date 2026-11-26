# Diffs, fragments et identifiants — référence exacte

## Identifiants déterministes

| Entité | Format | Exemple |
|---|---|---|
| Document | `lg:<juridiction>:<slug>` | `lg:fr:code-civil` |
| Nœud logique | `lg:…:<type>:<identifiant>` | `lg:fr:code-civil:article:1103` |
| Version | `lgv:<chemin du nœud>:<empreinte[0:16]>` | `lgv:fr:code-civil:article:1103:1c154e06503a8374` |
| Run d'ingestion | `run:<sha256[0:32] de (source, release, checksum)>` | `run:9f2c…` |

- L'identité **logique** (document, nœud) n'est JAMAIS dérivée du texte : un article renuméroté/écourté garde son identité tant que la continuité est établie ; sinon il faut un mapping explicite (`IdentityMapping`, relations `replaced_by`/`renumbered_to` uniquement sur preuve de source).
- L'empreinte de version est le SHA-256 des **faits sources immuables** : format, contenu, `upstream_version_id`, bornes de validité/effet, date de publication. Ressentir le même état source → même version (idempotence). Un seul de ces faits qui change → nouvelle version.

## Représentation et offsets

- Représentation unique en V1 : `content_format="plain_text"`, `representation_id="plain-text-v1"`.
- Unité d'offset : **point de code Unicode** (un `é` = 1, un emoji = 1), plages semi-ouvertes `[start, end)`.
- Un fragment est **version-scopé** : `GET /v1/node-versions/{version_id}/fragment?start&end&representation`. La représentation demandée doit correspondre à celle de la version, sinon `representation_mismatch` (400). Hors bornes → `invalid_range` (400). L'intégrité est vérifiée : le contenu stocké doit toujours hasher vers le `content_hash` enregistré, sinon `content_hash_mismatch` (409).
- Les offsets d'une version ne sont jamais réutilisés sur une autre sans revalidation (par construction, cf. tests).

## Diff de versions

- Endpoint : `GET /v1/nodes/{node_id}/diff?from={version_id}&to={version_id}`.
- Algorithme : `character-range-diff-v1` — script d'édition minimal (modèle insert/delete de Myers), LCS par programmation dynamique sur les points de code, regroupé en blocs `insert` / `delete` / `replace`.
- Réponse : plages `old_start/old_end` (version `from`) et `new_start/new_end` (version `to`) en points de code, textes old/new (nuls du côté non applicable : `old_text` d'un insert, `new_text` d'un delete), provenance des deux côtés, `is_legal_interpretation: false`.
- Plafond V1 documenté : le tableau LCS est limité à 16 M de cellules (≈ 4 000 × 4 000 points de code). Au-delà : erreur `diff_too_large`. Les diffs sont prévus au niveau **article** ; le seuil couvre largement les textes d'articles réels. Un vrai besoin plus large appellera l'implémentation Myers en espace linéaire (point d'extension documenté, ne pas optimiser prématurément).
- Un changement de ponctuation seul produit exactement un `replace` (testé, critère E).

## Snapshot de document et changes

- Un « snapshot » d'un document = un **run d'ingestion** : l'ensemble des versions observées dans une release amont (`node_version_observations`, y compris les versions inchangées ré-observées).
- `GET /v1/documents/{id}/changes?from={run}&to={run}` : opérations `node_added`, `node_removed`, `node_changed` (comparaison par empreinte de contenu), algorithme `document-snapshot-diff-v1`. Aucun effet juridique inféré ; les nœuds retirés d'une release gardent leur identité logique et leurs versions historiques.
