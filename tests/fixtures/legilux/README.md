# Fixtures Legilux (données réelles)

Fichiers téléchargés le 2026-11-24 depuis `http://data.legilux.public.lu`
(négociation de contenu sur les URI ELI), reproduits sans modification.

| fichier | URI | Accept |
|---|---|---|
| `loi-2012-07-21-jo.xml` | `/eli/etat/leg/loi/2012/07/21/n1/jo` | `application/xml` |
| `loi-2012-07-21.ttl` | même URI | `text/turtle` |
| `loi-1993-04-05-consolide.xml` | `/eli/etat/leg/loi/1993/04/05/n1/jo/consolide` | `application/xml` |
| `loi-1993-04-05.ttl` | `/eli/etat/leg/loi/1993/04/05/n1/jo/consolide` | `text/turtle` |
| `loi-2010-03-31-jo.xml` | `/eli/etat/leg/loi/2010/03/31/n1/jo` | `application/xml` |
| `loi-2010-03-31.ttl` | même URI | `text/turtle` |

- **Loi du 21 juillet 2012** (assistance mutuelle recouvrement, transposition
  directive 2010/24/UE) : 34 articles, 4 chapitres — acte court, idéal pour
  les tests.
- **Loi du 5 avril 1993** (secteur financier) : 66 articles, 6 parties,
  8 chapitres — teste la hiérarchie parties/chapitres et un graphe de
  relations riche (cites ×10, modifies ×3, repeals ×7, transposes ×3).
- **Loi du 31 mars 2010** (approbation de conventions fiscales) : 8 articles
  + **24 annexes** (197 articles internes) — teste le comptage des annexes
  non mappées (jamais silencieusement ignorées) ; citée par la loi du
  21 juillet 2012 (test de résolution croisée des références).

Licence : CC BY 4.0 (manifestations) / Licence de réutilisation SCL
(consolidés). Source : Ministère d'État — Service central de législation
(Luxembourg), https://legilux.public.lu. Legilux demeure la source authentique
de publication ; ces données en sont une représentation technique.
