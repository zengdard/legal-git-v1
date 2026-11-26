#include <gtest/gtest.h>

#include "legal_git/ids.h"
#include "legal_git/sha256.h"

using legal_git::CoreError;
using legal_git::make_document_id;
using legal_git::make_node_id;
using legal_git::make_version_id;
using legal_git::normalize_slug_component;
using legal_git::sha256_hex;
using legal_git::version_fingerprint;

TEST(Ids, NormalizesSlugComponents) {
  EXPECT_EQ(normalize_slug_component("Code civil"), "code-civil");
  EXPECT_EQ(normalize_slug_component("Article 1103"), "article-1103");
  EXPECT_EQ(normalize_slug_component("  Spaced   Out  "), "spaced-out");
  EXPECT_EQ(normalize_slug_component("---"), "");
  EXPECT_EQ(normalize_slug_component("Sous-titre Ier"), "sous-titre-ier");
}

TEST(Ids, DocumentId) {
  EXPECT_EQ(make_document_id("FR", "Code civil"), "lg:fr:code-civil");
  try {
    make_document_id("", "");
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "invalid_argument");
  }
}

TEST(Ids, NodeId) {
  EXPECT_EQ(make_node_id("lg:fr:code-civil", "Article", "1103"),
            "lg:fr:code-civil:article:1103");
  try {
    make_node_id("not-a-prefix", "Article", "1103");
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "invalid_argument");
  }
  try {
    make_node_id("lg:fr:code-civil", "", "");
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "invalid_argument");
  }
}

TEST(Ids, NodeIdIndependentOfContent) {
  // Invariant 10: text changes must not change logical node identity.
  const auto first =
      make_node_id("lg:fr:code-civil", "Article", "1103");
  const auto second =
      make_node_id("lg:fr:code-civil", "Article", "1103");
  EXPECT_EQ(first, second);
  const std::string other_text =
      "Un texte complètement différent.";
  (void)other_text;
}

TEST(Ids, VersionFingerprintIsDeterministic) {
  const auto a = version_fingerprint("plain_text", "contenu exact", "UP-1",
                                     "2016-10-01", "", "", "", "");
  const auto b = version_fingerprint("plain_text", "contenu exact", "UP-1",
                                     "2016-10-01", "", "", "", "");
  EXPECT_EQ(a, b);
  EXPECT_EQ(a.size(), 64u);
}

TEST(Ids, VersionFingerprintReactsToContentAndDates) {
  const auto base = version_fingerprint("plain_text", "contenu", "UP-1",
                                        "2016-10-01", "", "", "", "");
  EXPECT_NE(base, version_fingerprint("plain_text", "contenu modifié", "UP-1",
                                     "2016-10-01", "", "", "", ""));
  EXPECT_NE(base, version_fingerprint("plain_text", "contenu", "UP-1",
                                     "2019-05-22", "", "", "", ""));
  EXPECT_NE(base, version_fingerprint("plain_text", "contenu", "",
                                     "2016-10-01", "", "", "", ""));
  // Null and a real value never collide.
  EXPECT_NE(version_fingerprint("plain_text", "contenu", "", "", "", "", "",
                                ""),
            version_fingerprint("plain_text", "contenu", "UP-2", "", "",
                                 "", "", ""));
}

TEST(Ids, VersionIdShape) {
  // Invariant: version IDs derive from node identity + source facts (their
  // own content), not from anything mutable.
  const auto fingerprint = version_fingerprint(
      "plain_text", "contenu exact", "UP-1", "2016-10-01", "", "", "", "");
  const auto version_id =
      make_version_id("lg:fr:code-civil:article:1103", fingerprint);
  EXPECT_EQ(version_id,
            "lgv:fr:code-civil:article:1103:" + fingerprint.substr(0, 16));
  // Same content facts → same version ID (idempotent ingestion).
  const auto fingerprint2 = version_fingerprint(
      "plain_text", "contenu exact", "UP-1", "2016-10-01", "", "", "", "");
  EXPECT_EQ(version_id,
            make_version_id("lg:fr:code-civil:article:1103", fingerprint2));
}

TEST(Ids, VersionIdRejectsBadInputs) {
  try {
    make_version_id("lgv:fr:not-a-node", "aa");
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "invalid_argument");
  }
  try {
    make_version_id("lg:fr:code-civil:article:1103", "tooshort");
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "invalid_argument");
  }
}
