# Couverture du corpus pilote et limites V1

## Couverture du corpus LEGI (déclaration validée)

Le pilote ingère le **vrai Code civil** depuis l'open data LEGI de la DILA
(stock `Freemium_legi_global_20261108-140000.tar.gz`, licence ouverte v2.0) :

| Indicateur (LGITEXT000006070721 au 2026-11-08) | Valeur |
|---|---|
| Fiches du paquet | 7 410 |
| Sections logiques | 932 (81 fiches de section = renommages partageant un cid) |
| Articles logiques | 3 531 |
| Versions d'articles | 6 348, avec dates réelles de validité (ex. art. 1103 : `1804-03-21 → 2016-10-01` puis `2016-10-01 →`) |
| Relations (`sens=source`) | 14 111 (citations, concordances…) |
| Liens `sens=cible` non-inféres | 27 061 (comptés, non transformés en relations) |
| Fiches `MODIFIE_MORT_NE` | 46 (skippées, code dédié, conservées dans l'artefact brut) |

Historique : couverture égale à ce que le stock LEGI expose par texte (les
versions antérieures présentes dans le paquet sont ingérées, y compris les
textes antérieurs à 2016). Aucune version n'est inventée au-delà.

## Limites connues de V1

| Sujet | Limite | Mitigation |
|---|---|---|
| Immuabilité des versions | Garde ORM + **TRIGGER base de données** (migration 0002) | Testée : UPDATE/DELETE bruts rejetés |
| Liens LEGI `sens=cible` | Non transformés en relations (la direction appartient à l'autre texte) | Comptés dans le rapport, conservés dans l'artefact brut |
| Articles sans parent résolu | Skippés avec code `legi_article_placement_unresolved` | Rien de silencieux : rapport + artefact brut |
| Taille des diffs | Plafond 16 M de cellules LCS (`diff_too_large`) | Diffs prévus par article ; extension : Myers espace linéaire |
| Pagination | Curseurs à offset opaque | Forme keyset-ready (`items/next_cursor/has_more`) |
| Authentification / rate limiting | API lecture publique en V1 pilote | Points d'extension prévus avant toute mise en production publique |
| Relations inter-documents | Uniquement ce que la source fournit (`<lien>`) | Jamais inférées de texte |
| S3 | Stockage FS local derrière l'interface `ObjectStore` | Interface déjà abstraite (`storage://…`) |
| Recherche plein-texte / vecteurs | Hors périmètre V1 | — |
| Suppression de nœud | Un nœud absent d'une release garde son identité et ses versions (jamais détruit) | C'est la sémantique voulue ; l'absence par release est visible via `/changes` |

## Limites connues de la source Legilux (LU)

| Sujet | Limite | Mitigation |
|---|---|---|
| Dates de validité par article | N'existent pas dans Legilux (pas de fiche datée par article) | Versions = états observés ; `version_semantics: "observed_state"` + `date_basis` dans les métadonnées ; `valid_from` = `dateEntryInForce` de l'acte, jamais présenté comme validité juridique de l'article |
| Historique consolidé | Seule la consolidation **courante** est exposée (`…/consolide` a une date) ; pas de consolidation à date arbitraire | Reconstruit par snapshots successifs comparés (diff V1) ou via le graphe `modifies` + `dateEntryInForce` |
| `<mod>` par article | Un acte modificatif ne dit pas machine-readable quel article il change | Parse du texte ou diff des consolidations ; jamais inféré silencieusement |
| Annexes (`<attachments>`) | Non mappées en V1 (numérotation par document en collision avec les articles) | Comptées dans le rapport (`attachments_skipped`, `attachment_articles_skipped`), conservées dans l'artefact brut |
| Actes antérieurs à ~1900 | ~20 % sans XML (PDF uniquement) | Non couverts par l'adaptateur ; à traiter explicitement si nécessaire |
| Veille / découverte | Pas d'API de recherche publique fiable (SPARQL → SPA, 2026-11) | Énumération d'ELI explicites ; Mémoriaux énumérables en contournement |
| Relations inter-actes | Cibles non importées restent `unresolved` (clé `legilux:<ELI>` stable) | `relink` automatique dès import de la cible ; jamais de résolution par similarité |
| `inForceStatus` | Parse défensif du RDF Turtle (endpoint LOD instable) | Absence = `null`, jamais deviné |

## Non-goals assumés (spec V1)

Pas d'interprétation juridique, pas d'extraction d'obligations, pas d'AST,
pas de graphe normatif, pas de moteur de règles, pas de décision de
conformité, pas d'intégration LLM dans les enregistrements canoniques.
