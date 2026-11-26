#include <gtest/gtest.h>

#include <string>

#include "legal_git/sha256.h"

using legal_git::sha256_hex;
using legal_git::Sha256;

TEST(Sha256, EmptyInput) {
  EXPECT_EQ(sha256_hex(""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
}

TEST(Sha256, Abc) {
  EXPECT_EQ(sha256_hex("abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
}

TEST(Sha256, StreamingMatchesOneShot) {
  Sha256 streaming;
  streaming.update(reinterpret_cast<const uint8_t*>("ab"), 2);
  streaming.update(reinterpret_cast<const uint8_t*>("c"), 1);
  const auto digest = streaming.finish();

  const auto oneshot = legal_git::sha256("abc");
  ASSERT_EQ(digest.size(), oneshot.size());
  for (std::size_t i = 0; i < digest.size(); ++i) {
    EXPECT_EQ(digest[i], oneshot[i]);
  }
  EXPECT_EQ(sha256_hex("abc"), legal_git::sha256_hex("abc"));
}

TEST(Sha256, MillionA) {
  // Well-known vector: SHA-256 of one million 'a' characters.
  const std::string chunk(1000, 'a');
  Sha256 streaming;
  for (int i = 0; i < 1000; ++i) {
    streaming.update(reinterpret_cast<const uint8_t*>(chunk.data()),
                      chunk.size());
  }
  const auto digest = streaming.finish();
  std::string hex;
  static const char* kHex = "0123456789abcdef";
  for (uint8_t byte : digest) {
    hex.push_back(kHex[byte >> 4]);
    hex.push_back(kHex[byte & 0x0F]);
  }
  EXPECT_EQ(hex,
            "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0");
}

TEST(Sha256, DistinctInputs) {
  EXPECT_NE(sha256_hex("a"), sha256_hex("b"));
  // Byte-for-byte preservation matters: one byte of difference only.
  const std::string with_dot = "tiennent lieu de loi.";
  const std::string with_comma = "tiennent lieu de loi,";
  EXPECT_NE(sha256_hex(with_dot), sha256_hex(with_comma));
}
