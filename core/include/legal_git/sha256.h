#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>

namespace legal_git {

// Streaming SHA-256 (FIPS 180-4), used for deterministic content hashes.
class Sha256 {
 public:
  Sha256();

  void update(const uint8_t* data, std::size_t len);

  // Finalizes the digest. The instance must not be reused afterwards.
  std::array<uint8_t, 32> finish();

 private:
  void process_block(const uint8_t* block);

  uint32_t state_[8];
  uint8_t buffer_[64];
  std::size_t buffer_len_;
  uint64_t total_bits_;
};

// One-shot helpers over raw bytes.
std::array<uint8_t, 32> sha256(std::string_view bytes);

// Lowercase hex digest of the input bytes (no prefix).
std::string sha256_hex(std::string_view bytes);

}  // namespace legal_git
