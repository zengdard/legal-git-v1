# Export de corpus (bulk)

## Endpoints

- `GET /v1/exports` — manifeste des corpus disponibles (comptes par type, lien de téléchargement).
- `GET /v1/exports/{corpus_id}` — téléchargement NDJSON (`application/x-ndjson`).

## Format

Un enregistrement JSON **par ligne** (JSON strict, `ensure_ascii=False`, clés triées, ordre des enregistrements déterministe) :

```
{"type": "manifest", ...}        # 1 ligne : comptes, source, note d'autorité
{"type": "document", ...}         # 1 ligne : le document logique
{"type": "node", ...}             # la hiérarchie complète (parent_id inclus)
{"type": "node_version", ...}     # TOUTES les versions (contenu exact + hash)
{"type": "relationship", ...}    # citations/contexte (hors hiérarchie)
```

## Intégrité

L'en-tête `X-LegalGit-Export-Sha256` contient le SHA-256 exact du corps de la réponse. Vérification côté consommateur :

```python
import hashlib, httpx
r = httpx.get("http://localhost:8000/v1/exports/lg:fr:code-civil")
assert r.headers["x-legalgit-export-sha256"] == "sha256:" + hashlib.sha256(r.content).hexdigest()
records = [json.loads(line) for line in r.text.splitlines()]
```

Un consommateur n'a **aucun parser du paquet source à écrire** : IDs stables, hiérarchie, versions, provenance et contenus exacts arrivent déjà normalisés (critères F et G).

## Champs des `node_version` exportés

`id`, `node_id`, `source_id`, `ingestion_run_id`, `upstream_version_id`,
`content`, `content_format`, `content_hash`, `representation_id`,
`valid_from`, `valid_to`, `published_at`, `effective_from`, `effective_to`,
`ingested_at` (ISO 8601, nulls explicites — jamais de dates inventées).
