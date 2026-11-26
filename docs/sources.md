# Sources d'ingestion

## LEGI — open data DILA (câblé, source de production)

`import-legi` ingère le vrai corpus LEGI ([echanges.dila.gouv.fr/OPENDATA/LEGI](https://echanges.dila.gouv.fr/OPENDATA/LEGI/)) :

```bash
# 1. récupérer le dernier stock global (obligation : partir du dernier stock)
curl -O https://echanges.dila.gouv.fr/OPENDATA/LEGI/Freemium_legi_global_20261108-140000.tar.gz
# extraire (tar listant ~5,9 M de fiches ; extraire le seul Code civil ~ 40 Mo)
tar xzf Freemium_legi_global_*.tar.gz --wildcards "*/LEGITEXT000006070721/*"

# 2. importer (idempotent ; rejouer ne crée rien)
LEGALGIT_DATABASE_URL=... python -m app.ingestion.cli import-legi \
    --dir extraits/ --texte LEGITEXT000006070721 \
    --release "Freemium_legi_global_20261108-140000.tar.gz"

# 3. rester à jour : incrément quotidien du lendemain, même commande
tar xzf LEGI_20261124-*.tar.gz && python -m app.ingestion.cli import-legi \
    --dir <extrait du jour>/ --texte LEGITEXT000006070721 --release "LEGI_20261124"
```

### Modèle d'identité (preuves par la source, zéro inférence)

| Entité canonique | Clé d'identité LEGI | Preuve de continuité |
|---|---|---|
| Document | `cid` du texte (`LEGITEXT000006070721`) | LEGI lui-même |
| Section (nœud) | `cid` de section (`LEGISCTA…`) | stable à travers les renommages (Titre III « Des contrats… » → « Des sources d'obligations » garde son cid) |
| Article (nœud) | composante connexe des fiches reliées par leur liste `VERSIONS/LIEN_ART` | la liste VERSIONS, identique dans toutes les fiches d'un même article |
| Version d'article | id de fiche `LEGIARTI…` + dates (`DATE_DEBUT`/`DATE_FIN`) | la fiche elle-même (une fiche = une version immuable) |

Cas remarquables rencontrés dans les données réelles et traitement :

- **Renommage de section** (2016) : même `cid` → même nœud logique ; le titre
  du nœud suit la fiche la plus récente ; l'ancien placement reste dans les
  métadonnées de version (`tm_chain`).
- **`MODIFIE_MORT_NE`** (37 fiches dans le Code civil) : `DATE_FIN` antérieure
  à `DATE_DEBUT` dans la source. L'invariant canonique (`valid_to ≥ valid_from`)
  est préservé : fiches **skippées avec le code `legi_modifie_mort_ne`**,
  jamais normalisées silencieusement ; conservées dans l'artefact brut.
- **Contenu identique, faits sources distincts** : deux fiches peuvent
  porter le même texte (ids LEGIARTI différents) ; l'identité de version est
  l'empreinte de TOUS les faits sources, pas le hash seul.
- **Renchaînement d'identité par numéro** : jamais supposé — un numéro
  réutilisé avec une liste VERSIONS différente est un conflit enregistré
  (`legi_identity_conflict`), pas une fusion silencieuse.

### Chaîne de traitement

Parseurs C++ (`core/src/legi.cpp`, GoogleTests dédiés) : `parse_legi_article`,
`parse_legi_section`, `parse_legi_struct`, `parse_legi_version`. Le contenu
`BLOC_TEXTUEL/CONTENU` est conservé **exact** (fragments XHTML compris) sous
la représentation `xml-fragment-v1` ; la transformation documentée est le
décodage XML (entités/CDATA) et l'artefact brut (tar.gz déterministe du
sous-arbre, checksum du manifeste) est conservé pour chaque run.

### Licence et mentions (licence ouverte v2.0)

La source `legi` est enregistrée avec : paternité **DILA**, URL d'accès
`https://echanges.dila.gouv.fr/OPENDATA/LEGI/`, nom + date du fichier ingéré
(dans chaque rapport de run), licence « Licence ouverte v2.0 ». Chaque
rapport de run rappelle que **Légifrance demeure la source authentique de
publication**.

## Legilux — Journal officiel du Luxembourg (câblé, source de production)

`import-legilux` ingère le Journal officiel du Grand-Duché de Luxembourg via
le projet Casemates ([data.legilux.public.lu](http://data.legilux.public.lu),
Ministère d'État — Service central de législation) : URI **ELI** stables,
XML **Akoma Ntoso** et métadonnées **JOLUX** (RDF), par simple négociation de
contenu — pas de scraper, pas de PDF à reconstruire :

```bash
# un acte, texte d'origine (idempotent ; rejouer ne crée rien)
LEGALGIT_DATABASE_URL=… python -m app.ingestion.cli import-legilux \
    --eli etat/leg/loi/1993/04/05/n1/jo

# le texte consolidé courant de ce même acte
python -m app.ingestion.cli import-legilux --consolidated \
    --eli etat/leg/loi/1993/04/05/n1/jo

# hors-ligne / tests : fichiers locaux (téléchargés au préalable)
python -m app.ingestion.cli import-legilux --eli … --xml-file acte.xml --turtle-file acte.ttl
```

### Modèle d'identité (preuves par la source, zéro inférence)

| Entité canonique | Clé d'identité Legilux | Preuve de continuité |
|---|---|---|
| Document | l'URI ELI du `Work` (`…/eli/etat/leg/loi/1993/04/05/n1/jo`) | l'ELI lui-même (jamais le titre : les titres changent entre consolidations) |
| Section (nœud) | l'`id` du conteneur Akoma Ntoso (`partie_i.chapitre_1`) | stable à travers les consolidations du même acte |
| Article (nœud) | l'`id` de l'élément `<article>` (`art_1er`) | l'attribut AKN, preuve de continuité propre à la source |
| Version d'article | l'**état observé** du contenu du texte (d'origine ou consolidé) | l'empreinte des faits sources (contenu + variante + ELI) — Legilux n'expose pas de version par article |

Sémantique des versions — différence assumée avec LEGI : Legilux ne publie
pas de date de validité par article (pas de fiche datée comme `LEGIARTI`).
Les versions LU sont des **états observés** (`version_semantics:
"observed_state"` dans les métadonnées de version) : `valid_from` porte la
`dateEntryInForce` de l'ACTE (base enregistrée dans `date_basis`), et un
upstream modifié en place produira une nouvelle version observée au prochain
import. Rien n'est claiming une validité juridique par article.

### Relations (niveau acte)

Les prédicats JOLUX de l'acte deviennent des relations canoniques
**au niveau document** (`from_node_id` NULL, `from_document_id` porteur) :
`cites → cites`, `modifies → amends`, `repeals → repeals`,
`transposes → implements`. La cible est une clé stable `legilux:<ELI URI>`
(ou `eli:…` pour les directives UE) ; `relink_legilux_references` relie
rétroactivement une référence dès que l'acte cible est importé — pur
mapping d'identifiants, aucune inférence de texte.

### Chaîne de traitement

ParseAkoma Ntoso pur Python stdlib (`app/ingestion/legilux_adapter.py`,
`parse_akn_act`) : conteneurs `part/chapter/section` → nœuds `section`,
`<article id>` → nœuds `article`, contenu = fragment XML des blocs de l'article
sous la même représentation que LEGI (`xml-fragment-v1`, format
`xml_fragment`). Artefact brut (XML + RDF Turtle) conservé pour chaque run.
La couche V2 (AST, références, candidats de règles, graphe) fonctionne sur le
corpus LU sans adaptation (contenu de langue française) — attesté par les
tests `test_legilux_adapter.py`.

### Licence et mentions

Jeu de données « Legilux – Journal officiel » publié en **CC BY 4.0**
(data.public.lu) ; les textes consolidés portent la **Licence de
réutilisation SCL** (Ministère d'État, Service central de législation).
Chaque rapport de run porte l'attribution complète et rappelle que
**Legilux demeure la source authentique de publication** ; seuls les textes
publiés au Journal officiel du Grand-Duché de Luxembourg font foi.

### Périmètre et compléments choisis

- **Actes, pas codes consolidés** : l'unité de contenu Legilux est l'acte ;
  les codes (`/eli/etat/leg/code/…`) n'exposent pas de XML.
- **Annexes** (`<attachments>`, ex. 24 annexes / 197 articles dans la loi du
  31 mars 2010) : non mappées en V1 (numérotation par document, collision
  avec les articles de l'acte) — **comptées dans le rapport**
  (`attachments_skipped`, `attachment_articles_skipped`), conservées dans
  l'artefact brut, jamais silencieusement ignorées.
- **Découverte / veille** : pas d'API de recherche publique fiable (le
  endpoint SPARQL annoncé renvoie la SPA « Casemates » en 2026-11) ; les ELI
  à ingérer sont listés explicitement (cf. étude
  `docs/legilux-feasibility.md`).

## Corpus de démonstration (fixture)

La source `fixture-code-civil` (grammaire simplifiée, `evidence="fixture"`)
reste disponible pour les tests et la démo rapide (`import-fixtures`). Elle
ne prétend pas être le jeu de données officiel.
