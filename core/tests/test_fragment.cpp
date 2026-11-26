#include <gtest/gtest.h>

#include "legal_git/fragment.h"

using legal_git::CoreError;
using legal_git::extract_fragment;

TEST(Fragment, ExtractsMiddleRange) {
  const auto data = extract_fragment(
      "Les contrats légalement formés tiennent lieu de loi.", 4, 12,
      "unicode_code_point");
  EXPECT_EQ(data.text, "contrats");
  EXPECT_EQ(data.start, 4u);
  EXPECT_EQ(data.end, 12u);
  EXPECT_EQ(data.offset_unit, "unicode_code_point");
}

TEST(Fragment, EndMayEqualContentLength) {
  const std::string content = "loi.";
  const auto data =
      extract_fragment(content, 3, 4, "unicode_code_point");
  EXPECT_EQ(data.text, ".");
  EXPECT_EQ(data.content_length, 4u);
}

TEST(Fragment, EmptyRangeIsEmptyText) {
  const auto data =
      extract_fragment("abc", 1, 1, "unicode_code_point");
  EXPECT_TRUE(data.text.empty());
}

TEST(Fragment, AccentsUseCodePointOffsets) {
  // "éé" is two code points even though it is four UTF-8 bytes.
  const auto first =
      extract_fragment("éé", 0, 1, "unicode_code_point");
  EXPECT_EQ(first.text, "é");
  const auto second =
      extract_fragment("éé", 1, 2, "unicode_code_point");
  EXPECT_EQ(second.text, "é");
  EXPECT_EQ(second.content_length, 2u);
}

TEST(Fragment, AstralCharacterIsOneUnit) {
  const auto data =
      extract_fragment("😀!", 0, 1, "unicode_code_point");
  EXPECT_EQ(data.text, "😀");
}

TEST(Fragment, RejectsStartAfterEnd) {
  try {
    extract_fragment("abc", 2, 1, "unicode_code_point");
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "invalid_range");
  }
}

TEST(Fragment, RejectsEndBeyondContent) {
  // Offsets are version-scoped: a range legal in one version must be
  // rejected against a shorter one.
  try {
    extract_fragment("abc", 0, 4, "unicode_code_point");
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "invalid_range");
  }
}

TEST(Fragment, RejectsUnknownOffsetUnit) {
  try {
    extract_fragment("abc", 0, 1, "utf8_byte");
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "invalid_offset_unit");
  }
}

TEST(Fragment, RejectsInvalidUtf8Content) {
  try {
    extract_fragment(std::string("abc\xFF"), 0, 1, "unicode_code_point");
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "invalid_utf8");
  }
}
