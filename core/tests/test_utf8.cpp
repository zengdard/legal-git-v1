#include <gtest/gtest.h>

#include <string>

#include "legal_git/utf8.h"

using legal_git::CoreError;
using legal_git::utf8_decode;
using legal_git::utf8_encode;
using legal_git::utf8_length;

TEST(Utf8, DecodesAscii) {
  const auto cps = utf8_decode("");
  EXPECT_TRUE(cps.empty());
  EXPECT_EQ(utf8_length("abc"), 3u);
}

TEST(Utf8, AccentedFrenchCountsCodePoints) {
  // 13 code points, not bytes.
  const std::string text = "contrat légal";
  EXPECT_EQ(utf8_length(text), 13u);
}

TEST(Utf8, AstralPlaneCountsAsOne) {
  EXPECT_EQ(utf8_length("😀"), 1u);
}

TEST(Utf8, RoundTrips) {
  const std::string text =
      "« Les contrats légalement formés » 😀 — à ceux qui les ont faits.";
  const auto cps = utf8_decode(text);
  EXPECT_EQ(utf8_encode(cps), text);
}

TEST(Utf8, RejectsInvalidLeadByte) {
  try {
    utf8_decode(std::string("ok") + '\xFF');
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "invalid_utf8");
  }
}

TEST(Utf8, RejectsTruncatedSequence) {
  try {
    // 'é' is 0xC3 0xA9; keep the lead byte only.
    utf8_decode(std::string("abc") + '\xC3');
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "invalid_utf8");
  }
}

TEST(Utf8, RejectsBadContinuation) {
  try {
    utf8_decode(std::string("\xC3\x41"));
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "invalid_utf8");
  }
}

TEST(Utf8, RejectsSurrogate) {
  try {
    utf8_decode(std::string("\xED\xA0\x80"));
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "invalid_utf8");
  }
}

TEST(Utf8, RejectsOverlongEncoding) {
  try {
    // 0xC0 0x80 is an overlong encoding of NUL.
    utf8_decode(std::string("\xC0\x80"));
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "invalid_utf8");
  }
}

TEST(Utf8, EncodeRejectsSurrogateCodePoint) {
  try {
    std::u32string bad;
    bad.push_back(0xD800);
    utf8_encode(bad);
    FAIL() << "expected CoreError";
  } catch (const CoreError& e) {
    EXPECT_EQ(e.code, "invalid_code_point");
  }
}
