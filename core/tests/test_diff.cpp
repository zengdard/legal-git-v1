#include <gtest/gtest.h>

#include <string>
#include <vector>

#include "legal_git/diff.h"
#include "legal_git/utf8.h"

using legal_git::ChangeOperation;
using legal_git::CoreError;
using legal_git::diff_text;

namespace {

legal_git::Change single_change(const std::string& old_text,
                                const std::string& new_text) {
  const auto result = diff_text(old_text, new_text);
  EXPECT_EQ(result.changes.size(), 1u) << "expected exactly one change";
  EXPECT_EQ(result.algorithm, "character-range-diff-v1");
  EXPECT_EQ(result.offset_unit, "unicode_code_point");
  return result.changes.at(0);
}

}  // namespace

TEST(Diff, IdenticalTextsHaveNoChanges) {
  const auto result = diff_text("Les contrats légalement formés.",
                                "Les contrats légalement formés.");
  EXPECT_TRUE(result.changes.empty());
  EXPECT_EQ(result.algorithm, "character-range-diff-v1");
  EXPECT_EQ(result.offset_unit, "unicode_code_point");
}

TEST(Diff, PunctuationOnlyChangeIsDetectable) {
  // Acceptance criterion E: a punctuation-only change must be visible as a
  // replace with exact ranges (code points, half-open).
  const auto change = single_change(
      "Les contrats légalement formés.",
      "Les contrats légalement formés,");
  EXPECT_EQ(change.operation, ChangeOperation::Replace);
  EXPECT_EQ(change.old_text, ".");
  EXPECT_EQ(change.new_text, ",");
  EXPECT_EQ(change.old_start, 30u);
  EXPECT_EQ(change.old_end, 31u);
  EXPECT_EQ(change.new_start, 30u);
  EXPECT_EQ(change.new_end, 31u);
}

TEST(Diff, InsertOperationCarriesInsertionPoint) {
  const auto change = single_change("ab", "axb");
  EXPECT_EQ(change.operation, ChangeOperation::Insert);
  EXPECT_EQ(change.old_start, change.old_end);
  EXPECT_EQ(change.old_start, 1u);
  EXPECT_EQ(change.new_start, 1u);
  EXPECT_EQ(change.new_end, 2u);
}

TEST(Diff, DeleteOperationAnchorsInNewText) {
  const auto change = single_change("axb", "ab");
  EXPECT_EQ(change.operation, ChangeOperation::Delete);
  EXPECT_EQ(change.old_start, 1u);
  EXPECT_EQ(change.old_end, 2u);
  EXPECT_EQ(change.new_start, change.new_end);
  EXPECT_EQ(change.new_start, 1u);
}

TEST(Diff, EmptyToTextIsOneInsert) {
  const auto change = single_change("", "texte");
  EXPECT_EQ(change.operation, ChangeOperation::Insert);
  EXPECT_EQ(change.old_start, 0u);
  EXPECT_EQ(change.old_end, 0u);
  EXPECT_EQ(change.new_start, 0u);
  EXPECT_EQ(change.new_end, 5u);
}

TEST(Diff, AccentedCharacterOffsetsAreCodePoints) {
  // 'é' occupies two UTF-8 bytes but one code point: offsets must be 9, 10.
  const auto change = single_change("contrat légal", "contrat legal");
  EXPECT_EQ(change.operation, ChangeOperation::Replace);
  EXPECT_EQ(change.old_text, "é");
  EXPECT_EQ(change.new_text, "e");
  EXPECT_EQ(change.old_start, 9u);
  EXPECT_EQ(change.old_end, 10u);
  EXPECT_EQ(change.new_start, 9u);
  EXPECT_EQ(change.new_end, 10u);
}

TEST(Diff, AstralCharacterIsOneCodePoint) {
  const auto change = single_change("texte 😀 fin", "texte 🙁 fin");
  EXPECT_EQ(change.operation, ChangeOperation::Replace);
  EXPECT_EQ(change.old_start, 6u);
  EXPECT_EQ(change.old_end, 7u);
}

TEST(Diff, TwoSeparateRegionsProduceTwoChanges) {
  const auto result = diff_text("aaaXbbbYccc", "aaaZbbbWccc");
  ASSERT_EQ(result.changes.size(), 2u);
  EXPECT_EQ(result.changes[0].operation, ChangeOperation::Replace);
  EXPECT_EQ(result.changes[0].old_text, "X");
  EXPECT_EQ(result.changes[0].old_start, 3u);
  EXPECT_EQ(result.changes[0].new_text, "Z");
  EXPECT_EQ(result.changes[0].new_start, 3u);
  EXPECT_EQ(result.changes[1].old_text, "Y");
  EXPECT_EQ(result.changes[1].old_start, 7u);
}

TEST(Diff, AppliedChangesReconstructNewText) {
  // Property check: applying each change to the old text reproduces the new
  // text (in reverse order, since ranges are expressed on their own side).
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

  // Build the new text from changes: walk the old text, keeping equal parts,
  // substituting old ranges by new ranges, processing changes back-to-front.
  std::u32string old_cp = legal_git::utf8_decode(old_text);
  std::u32string new_cp = legal_git::utf8_decode(new_text);
  auto apply_forward = [&](std::u32string base) {
    for (const auto& change : result.changes) {
      const std::u32string replacement = legal_git::utf8_decode(change.new_text);
      base.replace(change.new_start, change.new_end - change.new_start,
                    replacement);
    }
    return base;
  };
  EXPECT_EQ(apply_forward(new_cp), new_cp) << "changes/Ranges must address the new side";

  auto apply_backward = [&](std::u32string base) {
    for (auto it = result.changes.rbegin(); it != result.changes.rend(); ++it) {
      const std::u32string replacement = legal_git::utf8_decode(it->new_text);
      base.replace(it->old_start, it->old_end - it->old_start, replacement);
    }
    return base;
  };
  EXPECT_EQ(apply_backward(old_cp), new_cp);
}

TEST(Diff, LargeInputsAreRejectedLoudly) {
  const std::string big1(5000, 'x');
  const std::string big2(5000, 'y');
  try {
    diff_text(big1, big2);
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "diff_too_large");
  }
}
