#include <gtest/gtest.h>

#include <string>

#include "legal_git/xml_corpus.h"

using legal_git::CoreError;
using legal_git::parse_corpus_xml;

namespace {

const char* kCorpus =
    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
    "<legal-git-corpus jurisdiction=\"fr\" slug=\"code-civil\" title=\"Code "
    "civil\" release-id=\"rel-demo-1\" evidence=\"fixture\">\n"
    "  <division type=\"livre\" id=\"fr:cc:livre:III\" num=\"III\" "
    "title=\"Des différentes manières dont on acquiert la propriété\">\n"
    "    <division type=\"titre\" id=\"fr:cc:titre:III\" num=\"III\" "
    "title=\"Des contrats ou des obligations conventionnelles en général\">\n"
    "      <article id=\"fr:cc:article:1103\" num=\"1103\" state=\"VIGUEUR\" "
    "version-id=\"DA1103\" valid-from=\"2016-10-01\">\n"
    "        <text>Les contrats légalement formés tiennent lieu de loi à ceux "
    "qui les ont faits.</text>\n"
    "        <lien type=\"CONTEXTE\" target=\"ordonnance-2016-131\" "
    "description=\"Issu de l'ordonnance n° 2016-131.\"/>\n"
    "      </article>\n"
    "      <article id=\"fr:cc:article:1106\" num=\"1106\" state=\"VIGUEUR\" "
    "version-id=\"DA1106\">\n"
    "        <text><![CDATA[Les conventions doivent être exécutées comme "
    "elles ont été faites.]]></text>\n"
    "      </article>\n"
    "      <note-editoriale/>\n"
    "    </division>\n"
    "  </division>\n"
    "</legal-git-corpus>\n";

}  // namespace

TEST(XmlCorpus, ParsesCorpusMetadata) {
  const auto data = parse_corpus_xml(kCorpus);
  ASSERT_TRUE(data.contains("corpus"));
  EXPECT_EQ(data["corpus"]["jurisdiction"], "fr");
  EXPECT_EQ(data["corpus"]["slug"], "code-civil");
  EXPECT_EQ(data["corpus"]["title"], "Code civil");
  EXPECT_EQ(data["corpus"]["release_id"], "rel-demo-1");
  EXPECT_EQ(data["corpus"]["evidence"], "fixture");
  EXPECT_EQ(data["corpus"]["document_type"], "code");
  EXPECT_TRUE(data["corpus"]["official_id"].is_null());
}

TEST(XmlCorpus, BuildsOrderedHierarchy) {
  const auto data = parse_corpus_xml(kCorpus);
  const auto& nodes = data["nodes"];
  ASSERT_EQ(nodes.size(), 4u);

  EXPECT_EQ(nodes[0]["upstream_id"], "fr:cc:livre:III");
  EXPECT_EQ(nodes[0]["node_type"], "livre");
  EXPECT_TRUE(nodes[0]["upstream_parent_id"].is_null());
  EXPECT_EQ(nodes[0]["order"], 0);
  EXPECT_EQ(nodes[0]["depth"], 0);

  EXPECT_EQ(nodes[1]["upstream_id"], "fr:cc:titre:III");
  EXPECT_EQ(nodes[1]["upstream_parent_id"], "fr:cc:livre:III");
  EXPECT_EQ(nodes[1]["depth"], 1);

  // Articles follow source order among their siblings.
  EXPECT_EQ(nodes[2]["upstream_id"], "fr:cc:article:1103");
  EXPECT_EQ(nodes[2]["upstream_parent_id"], "fr:cc:titre:III");
  EXPECT_EQ(nodes[2]["node_type"], "article");
  EXPECT_EQ(nodes[2]["order"], 0);
  EXPECT_EQ(nodes[2]["label"], "Article 1103");

  EXPECT_EQ(nodes[3]["upstream_id"], "fr:cc:article:1106");
  EXPECT_EQ(nodes[3]["order"], 1);
}

TEST(XmlCorpus, PreservesVersionTextAndDates) {
  const auto data = parse_corpus_xml(kCorpus);
  const auto& versions = data["versions"];
  ASSERT_EQ(versions.size(), 2u);

  EXPECT_EQ(versions[0]["node_upstream_id"], "fr:cc:article:1103");
  EXPECT_EQ(versions[0]["content"],
            "Les contrats légalement formés tiennent lieu de loi à ceux qui "
            "les ont faits.");
  EXPECT_EQ(versions[0]["content_format"], "plain_text");
  EXPECT_EQ(versions[0]["upstream_version_id"], "DA1103");
  EXPECT_EQ(versions[0]["valid_from"], "2016-10-01");
  EXPECT_TRUE(versions[0]["valid_to"].is_null());
  EXPECT_TRUE(versions[0]["published_at"].is_null());
  EXPECT_TRUE(versions[0]["effective_from"].is_null());
  EXPECT_TRUE(versions[0]["effective_to"].is_null());
  EXPECT_EQ(versions[0]["state"], "VIGUEUR");

  // CDATA is preserved byte-for-byte after XML decoding.
  EXPECT_EQ(versions[1]["content"],
            "Les conventions doivent être exécutées comme elles ont été "
            "faites.");
}

TEST(XmlCorpus, RecordsRelationshipsFromLiens) {
  const auto data = parse_corpus_xml(kCorpus);
  const auto& rels = data["relationships"];
  ASSERT_EQ(rels.size(), 1u);
  EXPECT_EQ(rels[0]["from_node_upstream_id"], "fr:cc:article:1103");
  EXPECT_EQ(rels[0]["relationship_type"], "related_to");
  EXPECT_EQ(rels[0]["upstream_type"], "CONTEXTE");
  EXPECT_EQ(rels[0]["target_upstream_id"], "ordonnance-2016-131");
  EXPECT_EQ(rels[0]["description"],
            "Issu de l'ordonnance n° 2016-131.");
}

TEST(XmlCorpus, RecordsUnsupportedElements) {
  const auto data = parse_corpus_xml(kCorpus);
  const auto& unsupported = data["unsupported"];
  ASSERT_FALSE(unsupported.empty());
  bool found = false;
  for (const auto& entry : unsupported) {
    if (entry["element"] == "note-editoriale") {
      found = true;
    }
  }
  EXPECT_TRUE(found) << "unknown elements must be recorded, never dropped";
}

TEST(XmlCorpus, RejectsDuplicateUpstreamIds) {
  const std::string bad =
      "<legal-git-corpus jurisdiction=\"fr\" slug=\"cc\" title=\"CC\" "
      "release-id=\"r\" evidence=\"fixture\">"
      "<division type=\"livre\" id=\"dup\" num=\"I\">"
      "<article id=\"dup\" num=\"1\"><text>a</text></article>"
      "</division></legal-git-corpus>";
  try {
    parse_corpus_xml(bad);
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "parse_error");
  }
}

TEST(XmlCorpus, RejectsArticleWithoutText) {
  const std::string bad =
      "<legal-git-corpus jurisdiction=\"fr\" slug=\"cc\" title=\"CC\" "
      "release-id=\"r\" evidence=\"fixture\">"
      "<division type=\"livre\" id=\"a\" num=\"I\">"
      "<article id=\"b\" num=\"1\"/>"
      "</division></legal-git-corpus>";
  try {
    parse_corpus_xml(bad);
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "parse_error");
  }
}

TEST(XmlCorpus, RejectsMissingRoot) {
  try {
    parse_corpus_xml("<other/>");
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "parse_error");
  }
}

TEST(XmlCorpus, RejectsBadEvidenceValue) {
  const std::string bad =
      "<legal-git-corpus jurisdiction=\"fr\" slug=\"cc\" title=\"CC\" "
      "release-id=\"r\" evidence=\"guess\">"
      "<division type=\"livre\" id=\"a\" num=\"I\"/>"
      "</legal-git-corpus>";
  try {
    parse_corpus_xml(bad);
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "parse_error");
  }
}

TEST(XmlCorpus, RejectsMissingRequiredAttribute) {
  const std::string bad =
      "<legal-git-corpus jurisdiction=\"fr\" slug=\"cc\" "
      "release-id=\"r\" evidence=\"fixture\">"
      "<division type=\"livre\" id=\"a\" num=\"I\"/>"
      "</legal-git-corpus>";
  try {
    parse_corpus_xml(bad);
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "parse_error");
  }
}
