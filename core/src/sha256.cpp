#include "legal_git/sha256.h"

#include <algorithm>
#include <cstring>

namespace legal_git {

namespace {

constexpr uint32_t kRoundConstants[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
    0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
    0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
    0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};

inline uint32_t rotr(uint32_t value, unsigned count) {
  return (value >> count) | (value << (32 - count));
}

}  // namespace

Sha256::Sha256()
    : state_{0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
             0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19},
      buffer_len_{0},
      total_bits_{0} {}

void Sha256::process_block(const uint8_t* block) {
  uint32_t w[64];
  for (int t = 0; t < 16; ++t) {
    w[t] = (uint32_t(block[t * 4]) << 24) | (uint32_t(block[t * 4 + 1]) << 16) |
           (uint32_t(block[t * 4 + 2]) << 8) | uint32_t(block[t * 4 + 3]);
  }
  for (int t = 16; t < 64; ++t) {
    const uint32_t s0 = rotr(w[t - 15], 7) ^ rotr(w[t - 15], 18) ^ (w[t - 15] >> 3);
    const uint32_t s1 = rotr(w[t - 2], 17) ^ rotr(w[t - 2], 19) ^ (w[t - 2] >> 10);
    w[t] = w[t - 16] + s0 + w[t - 7] + s1;
  }

  uint32_t a = state_[0], b = state_[1], c = state_[2], d = state_[3];
  uint32_t e = state_[4], f = state_[5], g = state_[6], h = state_[7];

  for (int t = 0; t < 64; ++t) {
    const uint32_t S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
    const uint32_t ch = (e & f) ^ (~e & g);
    const uint32_t temp1 = h + S1 + ch + kRoundConstants[t] + w[t];
    const uint32_t S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
    const uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
    const uint32_t temp2 = S0 + maj;
    h = g; g = f; f = e; e = d + temp1;
    d = c; c = b; b = a; a = temp1 + temp2;
  }

  state_[0] += a; state_[1] += b; state_[2] += c; state_[3] += d;
  state_[4] += e; state_[5] += f; state_[6] += g; state_[7] += h;
}

void Sha256::update(const uint8_t* data, std::size_t len) {
  total_bits_ += static_cast<uint64_t>(len) * 8;
  while (len > 0) {
    const std::size_t take = std::min(len, std::size_t(64) - buffer_len_);
    std::memcpy(buffer_ + buffer_len_, data, take);
    buffer_len_ += take;
    data += take;
    len -= take;
    if (buffer_len_ == 64) {
      process_block(buffer_);
      buffer_len_ = 0;
    }
  }
}

std::array<uint8_t, 32> Sha256::finish() {
  // Padding: 0x80, zeros up to offset 56, then the original message length
  // as a 64-bit big-endian bit count. Padding bytes are injected directly
  // so that total_bits_ (the message length) is not modified.
  const uint64_t bit_count = total_bits_;
  buffer_[buffer_len_++] = 0x80;
  if (buffer_len_ > 56) {
    std::memset(buffer_ + buffer_len_, 0, 64 - buffer_len_);
    process_block(buffer_);
    buffer_len_ = 0;
  }
  std::memset(buffer_ + buffer_len_, 0, 56 - buffer_len_);
  for (int i = 0; i < 8; ++i) {
    buffer_[56 + i] = static_cast<uint8_t>(bit_count >> (56 - 8 * i));
  }
  process_block(buffer_);
  buffer_len_ = 0;

  std::array<uint8_t, 32> digest{};
  for (int i = 0; i < 8; ++i) {
    digest[i * 4] = static_cast<uint8_t>(state_[i] >> 24);
    digest[i * 4 + 1] = static_cast<uint8_t>(state_[i] >> 16);
    digest[i * 4 + 2] = static_cast<uint8_t>(state_[i] >> 8);
    digest[i * 4 + 3] = static_cast<uint8_t>(state_[i]);
  }
  return digest;
}

std::array<uint8_t, 32> sha256(std::string_view bytes) {
  Sha256 hash;
  hash.update(reinterpret_cast<const uint8_t*>(bytes.data()), bytes.size());
  return hash.finish();
}

std::string sha256_hex(std::string_view bytes) {
  static const char* kHex = "0123456789abcdef";
  const auto digest = sha256(bytes);
  std::string out;
  out.reserve(digest.size() * 2);
  for (uint8_t byte : digest) {
    out.push_back(kHex[byte >> 4]);
    out.push_back(kHex[byte & 0x0F]);
  }
  return out;
}

}  // namespace legal_git
