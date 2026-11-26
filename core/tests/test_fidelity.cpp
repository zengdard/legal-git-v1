// Text fidelity tests (category 2 of the test specification): Legal Git
// must never modify the original text and must detect every meaningful
// change. Table-driven over the canonical cases.
//
// Property under test: with the exception of the documented XML decoding,
// the stored/restituted content is byte-for-byte the source content; any
// single-character change (punctuation, accent, negation) is detected.
#include <gtest/gtest.h>

#include <string>

#include "legal_git/diff.h"
#include "legal_git/utf8.h"

using legal_git::ChangeOperation;
using legal_git::DiffResult;
using legal_git::diff_text;

namespace {

struct FidelityCase {
  const char* label;
  std::string old_text;
  std::string new_text;
  bool expect_changes;
  int expect_min_changes;   // minimum number of change blocks
  const char* expect_op;    // dominant operation (or nullptr)
};

// The canonical fidelity corpus: every row is a legal-meaning-sensitive
// transformation and its expected detection. The decisive check applied
// to EVERY row is the exact-reconstruction property (no lost, invented or
// shifted content), plus detection and block validity.
const FidelityCase kCases[] = {
    {"identical", "Texte identique.", "Texte identique.", false, 0, nullptr},
    {"comma_added", "Les incidents sont notifiés sauf exception.",
     "Les incidents sont notifiés, sauf exception.", true, 1, "insert"},
    {"comma_removed", "Les incidents sont notifiés, sauf exception.",
     "Les incidents sont notifiés sauf exception.", true, 1, "delete"},
    {"comma_replaced_by_semicolon", "notifiés, sauf", "notifiés; sauf",
     true, 1, "replace"},
    {"accent_changed", "portee de la clause", "portée de la clause",
     true, 1, "insert"},
    {"negation_removed", "Cette clause n'est pas facultative.",
     "Cette clause est facultative.", true, 2, "delete"},
    {"negation_added", "La sanction est encourue.",
     "La sanction n'est pas encourue.", true, 2, "insert"},
    {"alinea_modified", "Premier alinéa inchangé. Second alinéa modifié ici.",
     "Premier alinéa inchangé. Second alinéa réécrit entièrement.", true, 1,
     "replace"},
    {"paragraph_added",
     "Premier paragraphe.",
     "Premier paragraphe.\nSecond paragraphe ajouté.", true, 1, "insert"},
    {"paragraph_removed", "Premier paragraphe.\nSecond paragraphe supprimé.",
     "Premier paragraphe.", true, 1, "delete"},
    {"single_character_in_middle", "obligation_ABCD_efgh",
     "obligation_ABCX_efgh", true, 1, "replace"},
    {"unicode_roundtrip", "« à â é è ê ë î ï ô ö ù ü û ç »",
     "« à â é è ê ë î ï ô ö ù ü û ç »", false, 0, nullptr},
    {"emoji_changed", "Article 1 — non applicable 😀",
     "Article 1 — non applicable 😀", false, 0, nullptr},
    {"emoji_replaced", "applicable 😀", "applicable 🙂",
     true, 1, "replace"},
    {"multibyte_typographic_quotes", "elle prévoit \"une limite\"",
     "elle prévoit « une limite »", true, 2, "replace"},
    // Single space added vs removed (invisible but legally meaningful).
    {"space_added", "délai detrente jours", "délai de trente jours", true, 1,
     nullptr},
    {"hyphen_removed", "sous-direction générale", "sous direction générale",
     true, 1, "replace"},
    {"both_ends_trimmed_content_unchanged", " x ", " x ", false, 0, nullptr},
};

}  // namespace

class TextFidelity : public ::testing::TestWithParam<FidelityCase> {};

TEST_P(TextFidelity, DetectsExactlyWhatChanged) {
  const FidelityCase& case_ = GetParam();
  const DiffResult result = diff_text(case_.old_text, case_.new_text);

  if (!case_.expect_changes) {
    EXPECT_TRUE(result.changes.empty())
        << case_.label << ": identical texts must produce no change";
    return;
  }

  ASSERT_FALSE(result.changes.empty()) << case_.label << ": change NOT detected";
  EXPECT_GE(static_cast<int>(result.changes.size()), case_.expect_min_changes)
      << case_.label;
  EXPECT_EQ(result.algorithm, "character-range-diff-v1");

  bool saw_expected_op = false;
  for (const auto& change : result.changes) {
    const char* op =
        change.operation == ChangeOperation::Insert
            ? "insert"
            : (change.operation == ChangeOperation::Delete ? "delete"
                                                             : "replace");
    if (case_.expect_op != nullptr && op == std::string(case_.expect_op)) {
      saw_expected_op = true;
    }
    // Ranges are valid half-open code point ranges on their own side.
    EXPECT_LE(change.old_start, change.old_end);
    EXPECT_LE(change.new_start, change.new_end);
    if (op == std::string("replace")) {
      EXPECT_LT(change.old_start, change.old_end);
      EXPECT_LT(change.new_start, change.new_end);
    } else if (op == std::string("insert")) {
      EXPECT_EQ(change.old_start, change.old_end);
      EXPECT_FALSE(change.new_text.empty());
    } else {  // delete
      EXPECT_EQ(change.new_start, change.new_end);
      EXPECT_FALSE(change.old_text.empty());
    }
  }
  if (case_.expect_op != nullptr) {
    EXPECT_TRUE(saw_expected_op)
        << case_.label << ": expected a '" << case_.expect_op << "' block";
  }

  // THE fidelity property, on every single case: applying the changes
  // backward to the old text rebuilds the new text byte for byte. Any
  // lost, invented, truncated or shifted content fails here.
  std::u32string rebuilt = legal_git::utf8_decode(case_.old_text);
  for (auto it = result.changes.rbegin(); it != result.changes.rend(); ++it) {
    rebuilt.replace(it->old_start, it->old_end - it->old_start,
                    legal_git::utf8_decode(it->new_text));
  }
  EXPECT_EQ(legal_git::utf8_encode(rebuilt), case_.new_text)
      << case_.label << ": reconstruction mismatch";
}

INSTANTIATE_TEST_SUITE_P(CanonicalCases, TextFidelity,
                         ::testing::ValuesIn(std::begin(kCases),
                                             std::end(kCases)),
                         [](const ::testing::TestParamInfo<FidelityCase>& info) {
                           return info.param.label;
                         });

// Fidelity property: applying the changes of a diff to the old text always
// reconstructs the new text exactly (no lost or invented content in between).
// Application is done BACKWARD on the old text: removals use old ranges,
// insertions carry their own text, so earlier old offsets stay valid.
TEST(DiffReconstruction, ChangesRebuildTheNewTextExactly) {
  const std::string old_text =
      "Les conventions obligent non seulement à ce qui y est exprimé, mais "
      "encore à toutes les suites que l'équité, l'usage ou la loi donnent à "
      "l'obligation d'après sa nature.";
  const std::string new_text =
      "Les conventions obligent uniquement à ce qui y est exprimé, mais "
      "encore à toutes les suites supplémentaires que l'équité, l'usage ou "
      "la loi donnent à l'obligation conformément à sa nature exacte.";
  const auto result = diff_text(old_text, new_text);
  ASSERT_FALSE(result.changes.empty());

  std::u32string base = legal_git::utf8_decode(old_text);
  for (auto it = result.changes.rbegin(); it != result.changes.rend(); ++it) {
    const std::u32string replacement =
        legal_git::utf8_decode(it->new_text.empty() ? "" : it->new_text);
    base.replace(it->old_start, it->old_end - it->old_start, replacement);
  }
  EXPECT_EQ(legal_git::utf8_encode(base), new_text);
}

// No truncation: a maximal-size text (doc: 16 M LCS cells cap) must diff
// without data loss, and a change at the very end must be found. Larger
// inputs are REFUSED loudly (see Diff.LargeInputsAreRejectedLoudly).
// NB: the corpus is made of UNIQUE sentences: on repetitive texts the
// minimal alignment is ambiguous and the block may anchor at an equivalent
// position (reconstruction stays exact; absolute offsets are only pinned
// by unambiguous content).
TEST(NoTruncation, MaximalSizeChangeAtTheEndIsDetected) {
  std::string long_old;
  for (std::size_t i = 0; i < 120u; ++i) {
    long_old += "article numero " + std::to_string(i) + " du dispositif. ";
  }
  long_old.pop_back();  // ends with the period
  const std::size_t n = long_old.size();
  ASSERT_GT(n, 3'000u);
  ASSERT_LE(n * n, 16'000'000u);  // within the documented cap
  std::string long_new = long_old;
  long_new.back() = '!';
  const auto result = diff_text(long_old, long_new);
  ASSERT_EQ(result.changes.size(), 1u);
  EXPECT_EQ(result.changes[0].operation, ChangeOperation::Replace);
  EXPECT_EQ(result.changes[0].old_text, ".");
  EXPECT_EQ(result.changes[0].new_text, "!");
  EXPECT_EQ(result.changes[0].old_start + 1, n);
  // Reconstruction over the full text proves no truncation happened.
  std::u32string base = legal_git::utf8_decode(long_old);
  const auto& change = result.changes[0];
  base.replace(change.old_start, change.old_end - change.old_start,
               legal_git::utf8_decode(change.new_text));
  EXPECT_EQ(legal_git::utf8_encode(base), long_new);
}

// Empty text behaviour: defined, not an error.
TEST(EmptyTexts, EmptyToEmptyIsEmptyDiff) {
  const auto result = diff_text("", "");
  EXPECT_TRUE(result.changes.empty());
}

TEST(EmptyTexts, EmptyToTextIsOneInsert) {
  const auto result = diff_text("", "Texte nouveau.");
  ASSERT_EQ(result.changes.size(), 1u);
  EXPECT_EQ(result.changes[0].operation, ChangeOperation::Insert);
  EXPECT_EQ(result.changes[0].new_text, "Texte nouveau.");
}

TEST(EmptyTexts, TextToEmptyIsOneDelete) {
  const auto result = diff_text("Texte abrogé.", "");
  ASSERT_EQ(result.changes.size(), 1u);
  EXPECT_EQ(result.changes[0].operation, ChangeOperation::Delete);
  EXPECT_EQ(result.changes[0].old_text, "Texte abrogé.");
}

// Negation sensitivity, legal wording: removing a "pas" must be detected
// as a deletion of exactly that word (with its trailing separator).
TEST(LegallySensitive, RemovingPasIsAnExactDeletion) {
  const std::string old_text =
      "Le transporteur n'est pas responsable des retards.";
  const std::string new_text =
      "Le transporteur n'est responsable des retards.";
  const auto result = diff_text(old_text, new_text);
  ASSERT_EQ(result.changes.size(), 1u);
  const auto& change = result.changes[0];
  EXPECT_EQ(change.operation, ChangeOperation::Delete);
  EXPECT_EQ(change.old_text, "pas ");
  // The deletion is anchored in the new text at the position where the
  // word was removed.
  EXPECT_EQ(change.new_start, change.new_end);
  EXPECT_LT(change.new_start, new_text.size());
}
