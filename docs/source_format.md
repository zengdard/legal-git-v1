# Format des corpus XML (grammaire du cœur C++)

Le cœur C++ (`core/src/xml_corpus.cpp`) parse cette grammaire. Le fixture
`fixtures/code-civil/` en est la référence exécutable.

```xml
<legal-git-corpus
    jurisdiction="fr"            <!-- requis, ex. "fr" -->
    slug="code-civil"            <!-- requis, slug du document -->
    title="Code civil"           <!-- requis -->
    document-type="code"         <!-- optionnel, défaut "code" -->
    release-id="demo-2024-06"    <!-- requis, identifiant de release amont -->
    evidence="fixture"           <!-- requis : "official" | "fixture" -->
    official-id="LEGITEXT...">   <!-- optionnel -->

  <division                      <!-- conteneur structurel récursif -->
      type="livre|titre|..."     <!-- requis -->
      id="fr:cc:livre:III"       <!-- requis, unique dans le corpus -->
      num="III"                  <!-- optionnel -->
      label="Livre III"          <!-- optionnel (défaut : type + num) -->
      title="Des différentes..."><!-- optionnel -->

    <article
        id="fr:cc:article:1103"  <!-- requis, unique dans le corpus -->
        num="1103"               <!-- requis -->
        state="VIGUEUR"          <!-- optionnel, conservé tel quel -->
        version-id="ARTI-2016"   <!-- optionnel, id de VERSION amont -->
        valid-from="2016-10-01" <!-- optionnel, null si absent -->
        valid-to="2999-01-01"    <!-- optionnel -->
        published-at="..." effective-from="..." effective-to="..."  <!-- idem -->
        demo-only="true">        <!-- optionnel, flag de démonstration -->

      <text>Exact text…</text>    <!-- requis, exactement un ; CDATA admis -->
      <lien type="CONTEXTE" target="ordonnance-2016-131"
            description="…"/>     <!-- optionnel, citations/contexte -->
    </article>
  </division>
</legal-git-corpus>
```

## Règles de conservation

- **Texte** : le contenu de `<text>` est conservé byte-for-byte après décodage XML (entités `&…;`, CDATA). Aucune normalisation (pas de repli `\r\n` → `\n`, pas de trim). La transformation « décodage XML → plain text » est documentée et l'artefact brut est conservé par l'ingestion.
- **Éléments inconnus** : tout élément non reconnu est enregistré dans `unsupported[]` du rapport d'import — jamais silencieusement ignoré.
- **Types de `<lien>`** mappés : `CITATION`→`cites`, `CONTEXTE`→`related_to`, `ABROGATION`→`repeals`, `MODIFICATION`→`amends`, `CREATION`→`related_to` ; type inconnu → `related_to` avec `upstream_type` conservé en métadonnée.
- **Doublons d'`id`**, article sans `<text>`, attributs requis manquants, `evidence` invalide → erreur `parse_error`, import atomique abandonné.

## Schéma vers le modèle canonique

| XML | Canonique |
|---|---|
| `jurisdiction`, `slug` | `Document.id = lg:<jurisdiction>:<slug>` |
| `division|article` + `num` | `Node.id = lg:…:<type>:<identifier>` (identité indépendante du texte) |
| `text` + dates + `version-id` | `NodeVersion` (empreinte = SHA-256 des faits sources) |
| `lien` | `Relationship` (distinct de la hiérarchie parent/enfant) |
