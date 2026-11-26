// LEGI fiche parser tests. The inline fiches are simplified but faithful
// excerpts of the real DILA LEGI open data distribution (licence ouverte
// v2.0), based on actual Code civil fiches (e.g. LEGIARTI000032040777).
#include <gtest/gtest.h>

#include <string>

#include "legal_git/legi.h"

using legal_git::CoreError;
using legal_git::parse_legi_article;
using legal_git::parse_legi_section;
using legal_git::parse_legi_struct;
using legal_git::parse_legi_version;

namespace {

const char* kArticle = R"(<?xml version="1.0" encoding="UTF-8"?>
<ARTICLE>
<META>
<META_COMMUN>
<ID>LEGIARTI000032040777</ID>
<ANCIEN_ID/>
<ORIGINE>LEGI</ORIGINE>
<NATURE>Article</NATURE>
</META_COMMUN>
<META_SPEC>
<META_ARTICLE>
<NUM>1103</NUM>
<ETAT>VIGUEUR</ETAT>
<DATE_DEBUT>2016-10-01</DATE_DEBUT>
<DATE_FIN>2999-01-01</DATE_FIN>
<TYPE>AUTONOME</TYPE>
</META_ARTICLE>
</META_SPEC>
</META>
<CONTEXTE>
<TEXTE cid="LEGITEXT000006070721" nature="CODE">
<TITRE_TXT c_titre_court="Code civil" id_txt="LEGITEXT000006070721">Code civil</TITRE_TXT>
<TM>
<TITRE_TM id="LEGISCTA000006090271">Livre III : Des différentes manières dont on acquiert la propriété</TITRE_TM>
<TM>
<TITRE_TM id="LEGISCTA000032040794">Titre III : Des sources d'obligations</TITRE_TM>
<TM>
<TITRE_TM id="LEGISCTA000032006712">Sous-titre Ier :  Le contrat </TITRE_TM>
</TM>
</TM>
</TM>
</TEXTE>
</CONTEXTE>
<VERSIONS>
<VERSION etat="MODIFIE">
<LIEN_ART debut="1804-03-21" etat="MODIFIE" fin="2016-10-01" id="LEGIARTI000006436088" num="1103" origine="LEGI"/>
</VERSION>
<VERSION etat="VIGUEUR">
<LIEN_ART debut="2016-10-01" etat="VIGUEUR" fin="2999-01-01" id="LEGIARTI000032040777" num="1103" origine="LEGI"/>
</VERSION>
</VERSIONS>
<BLOC_TEXTUEL>
<CONTENU>Les contrats légalement formés tiennent lieu de loi à ceux qui les ont faits. </CONTENU>
</BLOC_TEXTUEL>
<LIENS>
<LIEN cidtexte="LEGITEXT000006070721" id="LEGIARTI000006436298" num="1134" sens="source" typelien="CONCORDANCE">Code civil - art. 1134, alinéa 3 (M)</LIEN>
</LIENS>
</ARTICLE>
)";

}  // namespace

TEST(LegiArticle, ParsesMetadataAndDates) {
  const auto fiche = parse_legi_article(kArticle);
  EXPECT_EQ(fiche["kind"], "article");
  EXPECT_EQ(fiche["id"], "LEGIARTI000032040777");
  EXPECT_EQ(fiche["num"], "1103");
  EXPECT_EQ(fiche["etat"], "VIGUEUR");
  EXPECT_EQ(fiche["date_debut"], "2016-10-01");
  EXPECT_EQ(fiche["date_fin"], "2999-01-01");
  EXPECT_EQ(fiche["nature"], "Article");
}

TEST(LegiArticle, PreservesExactContentByteForByte) {
  const auto fiche = parse_legi_article(kArticle);
  // Note the trailing space: source text is never trimmed.
  EXPECT_EQ(fiche["contenu"],
            "Les contrats légalement formés tiennent lieu de loi à ceux qui "
            "les ont faits. ");
  EXPECT_EQ(fiche["contenu_format"], "xml_fragment");
  EXPECT_EQ(fiche["contenu_has_markup"], false);
}

TEST(LegiArticle, VersionListIsIdentityEvidence) {
  const auto fiche = parse_legi_article(kArticle);
  const auto& versions = fiche["versions"];
  ASSERT_EQ(versions.size(), 2u);
  EXPECT_EQ(versions[0]["id"], "LEGIARTI000006436088");
  EXPECT_EQ(versions[0]["etat"], "MODIFIE");
  EXPECT_EQ(versions[1]["id"], "LEGIARTI000032040777");
}

TEST(LegiArticle, ContexteGivesOrderedTmChain) {
  const auto fiche = parse_legi_article(kArticle);
  EXPECT_EQ(fiche["contexte"]["texte_cid"], "LEGITEXT000006070721");
  EXPECT_EQ(fiche["contexte"]["texte_nature"], "CODE");
  const auto& tms = fiche["contexte"]["tms"];
  ASSERT_EQ(tms.size(), 3u);
  EXPECT_EQ(tms[0]["id"], "LEGISCTA000006090271");
  EXPECT_EQ(tms[1]["id"], "LEGISCTA000032040794");
  EXPECT_EQ(tms[2]["titre"], "Sous-titre Ier :  Le contrat ");
}

TEST(LegiArticle, ParsesLiens) {
  const auto fiche = parse_legi_article(kArticle);
  const auto& liens = fiche["liens"];
  ASSERT_EQ(liens.size(), 1u);
  EXPECT_EQ(liens[0]["typelien"], "CONCORDANCE");
  EXPECT_EQ(liens[0]["sens"], "source");
  EXPECT_EQ(liens[0]["id"], "LEGIARTI000006436298");
  EXPECT_EQ(liens[0]["num"], "1134");
}

TEST(LegiArticle, MarkupContentKeepsInnerXml) {
  const auto fiche = parse_legi_article(
      R"(<ARTICLE>
<META><META_COMMUN><ID>LEGIARTI000000001</ID><ORIGINE>LEGI</ORIGINE><NATURE>Article</NATURE></META_COMMUN>
<META_SPEC><META_ARTICLE><NUM>2</NUM><ETAT>VIGUEUR</ETAT><DATE_DEBUT>2026-01-01</DATE_DEBUT><DATE_FIN>2999-01-01</DATE_FIN></META_ARTICLE></META_SPEC></META>
<CONTEXTE><TEXTE cid="LEGITEXT000006070721"><TITRE_TXT>Code civil</TITRE_TXT></TEXTE></CONTEXTE>
<VERSIONS><VERSION><LIEN_ART id="LEGIARTI000000001" num="2"/></VERSION></VERSIONS>
<BLOC_TEXTUEL><CONTENU><p>Premier alinéa.</p><p>Second <i>alinéa</i>.</p></CONTENU></BLOC_TEXTUEL>
<LIENS/>
</ARTICLE>)");
  EXPECT_EQ(fiche["contenu_has_markup"], true);
  // Raw inner serialization of the markup children, in order.
  EXPECT_EQ(fiche["contenu"],
            "<p>Premier alinéa.</p><p>Second <i>alinéa</i>.</p>");
}

TEST(LegiArticle, MissingContexteIsAnError) {
  try {
    parse_legi_article("<ARTICLE><META><META_COMMUN><ID>X</ID></META_COMMUN>"
                       "<META_SPEC><META_ARTICLE><NUM>1</NUM></META_ARTICLE>"
                       "</META_SPEC></META></ARTICLE>");
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "parse_error");
  }
}

namespace {

const char* kSection = R"(<?xml version="1.0" encoding="UTF-8"?>
<SECTION_TA>
<ID>LEGISCTA000032040792</ID>
<TITRE_TA>Chapitre Ier : Dispositions liminaires</TITRE_TA>
<STRUCTURE_TA>
<LIEN_ART debut="2016-10-01" etat="VIGUEUR" fin="2999-01-01" id="LEGIARTI000032040787" num="1101" origine="LEGI"/>
<LIEN_ART debut="2016-10-01" etat="VIGUEUR" fin="2999-01-01" id="LEGIARTI000032040782" num="1102" origine="LEGI"/>
<LIEN_SECTION_TA cid="LEGISCTA000006118073" id="LEGISCTA000032041884" niv="3" titre-url="...">Titre IV : Du régime général des obligations</LIEN_SECTION_TA>
</STRUCTURE_TA>
<CONTEXTE>
<TEXTE cid="LEGITEXT000006070721">
<TITRE_TXT>Code civil</TITRE_TXT>
<TM>
<TITRE_TM id="LEGISCTA000006090271">Livre III</TITRE_TM>
</TM>
</TEXTE>
</CONTEXTE>
</SECTION_TA>
)";

}  // namespace

TEST(LegiSection, ParsesTitleAndOrderedChildren) {
  const auto fiche = parse_legi_section(kSection);
  EXPECT_EQ(fiche["kind"], "section");
  EXPECT_EQ(fiche["id"], "LEGISCTA000032040792");
  EXPECT_EQ(fiche["titre_ta"], "Chapitre Ier : Dispositions liminaires");
  const auto& articles = fiche["children"]["articles"];
  ASSERT_EQ(articles.size(), 2u);
  EXPECT_EQ(articles[0]["id"], "LEGIARTI000032040787");
  EXPECT_EQ(articles[0]["order"], 0);
  EXPECT_EQ(articles[1]["num"], "1102");
  const auto& sections = fiche["children"]["sections"];
  ASSERT_EQ(sections.size(), 1u);
  // cid vs id: the logical identity vs the version fiche.
  EXPECT_EQ(sections[0]["cid"], "LEGISCTA000006118073");
  EXPECT_EQ(sections[0]["id"], "LEGISCTA000032041884");
}

namespace {

const char* kTextelr = R"(<?xml version="1.0" encoding="UTF-8"?>
<TEXTELR>
<META>
<META_COMMUN>
<ID>LEGITEXT000006070721</ID>
<ANCIEN_ID>CCIVILL0</ANCIEN_ID>
<ORIGINE>LEGI</ORIGINE>
<NATURE>CODE</NATURE>
</META_COMMUN>
<META_SPEC>
<META_TEXTE_CHRONICLE>
<CID>LEGITEXT000006070721</CID>
<DERNIERE_MODIFICATION>2026-07-29</DERNIERE_MODIFICATION>
</META_TEXTE_CHRONICLE>
</META_SPEC>
</META>
<VERSIONS>
<VERSION etat="VIGUEUR">
<LIEN_TXT debut="1804-03-21" etat="VIGUEUR" fin="2999-01-01" id="LEGITEXT000006070721"/>
</VERSION>
</VERSIONS>
<STRUCT>
<LIEN_SECTION_TA cid="LEGISCTA000006090271" debut="1804-03-21" etat="VIGUEUR" fin="2999-01-01" id="LEGISCTA000006090271" niv="1">Livre III : Des différentes manières dont on acquiert la propriété</LIEN_SECTION_TA>
</STRUCT>
</TEXTELR>
)";

}  // namespace

TEST(LegiStruct, ParsesTexteIdentityAndTopChildren) {
  const auto fiche = parse_legi_struct(kTextelr);
  EXPECT_EQ(fiche["kind"], "struct");
  EXPECT_EQ(fiche["id"], "LEGITEXT000006070721");
  EXPECT_EQ(fiche["ancien_id"], "CCIVILL0");
  EXPECT_EQ(fiche["cid"], "LEGITEXT000006070721");
  EXPECT_EQ(fiche["derniere_modification"], "2026-07-29");
  ASSERT_EQ(fiche["versions_texte"].size(), 1u);
  const auto& sections = fiche["children"]["sections"];
  ASSERT_EQ(sections.size(), 1u);
  EXPECT_EQ(sections[0]["cid"], "LEGISCTA000006090271");
  EXPECT_EQ(sections[0]["order"], 0);
}

TEST(LegiVersion, ParsesTitles) {
  const auto fiche = parse_legi_version(
      R"(<TEXTE_VERSION><META><META_COMMUN><ID>LEGITEXT000006070721</ID><NATURE>CODE</NATURE></META_COMMUN>
<META_SPEC><META_TEXTE_VERSION><TITRE>Code civil</TITRE><TITREFULL>Code civil</TITREFULL></META_TEXTE_VERSION></META_SPEC></META></TEXTE_VERSION>)");
  EXPECT_EQ(fiche["kind"], "texte_version");
  EXPECT_EQ(fiche["titre"], "Code civil");
  EXPECT_EQ(fiche["titrefull"], "Code civil");
}
