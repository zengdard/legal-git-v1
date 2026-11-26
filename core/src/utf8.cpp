#include "legal_git/utf8.h"

#include <cstdint>
#include <cstdio>

namespace legal_git {

namespace {

[[noreturn]] void fail(std::string code, const std::string& what) {
  throw CoreError(std::move(code), what);
}

}  // namespace

std::u32string utf8_decode(std::string_view text) {
  std::u32string out;
  out.reserve(text.size());
  std::size_t i = 0;
  while (i < text.size()) {
    const uint8_t lead = static_cast<uint8_t>(text[i]);
    std::size_t len;
    char32_t cp;
    if ((lead & 0x80) == 0x00) {
      len = 1;
      cp = lead & 0x7F;
    } else if ((lead & 0xE0) == 0xC0) {
      len = 2;
      cp = lead & 0x1F;
    } else if ((lead & 0xF0) == 0xE0) {
      len = 3;
      cp = lead & 0x0F;
    } else if ((lead & 0xF8) == 0xF0) {
      len = 4;
      cp = lead & 0x07;
    } else {
      fail("invalid_utf8", "invalid UTF-8 lead byte at offset " +
                               std::to_string(i));
    }
    if (i + len > text.size()) {
      fail("invalid_utf8", "truncated UTF-8 sequence at offset " +
                               std::to_string(i));
    }
    for (std::size_t k = 1; k < len; ++k) {
      const uint8_t cont = static_cast<uint8_t>(text[i + k]);
      if ((cont & 0xC0) != 0x80) {
        fail("invalid_utf8",
             "invalid UTF-8 continuation byte at offset " + std::to_string(i + k));
      }
      cp = (cp << 6) | (cont & 0x3F);
    }
    if ((len == 2 && cp < 0x80) || (len == 3 && cp < 0x800) ||
        (len == 4 && cp < 0x10000)) {
      fail("invalid_utf8",
            "overlong UTF-8 encoding at offset " + std::to_string(i));
    }
    if (cp >= 0xD800 && cp <= 0xDFFF) {
      fail("invalid_utf8", "UTF-16 surrogate in UTF-8 at offset " +
                               std::to_string(i));
    }
    if (cp > 0x10FFFF) {
      fail("invalid_utf8", "code point above U+10FFFF at offset " +
                               std::to_string(i));
    }
    out.push_back(cp);
    i += len;
  }
  return out;
}

std::string utf8_encode(std::u32string_view code_points) {
  std::string out;
  out.reserve(code_points.size());
  for (char32_t cp : code_points) {
    if (cp >= 0xD800 && cp <= 0xDFFF) {
      fail("invalid_code_point",
           "cannot encode UTF-16 surrogate U+" + [&] {
             char buf[16];
             std::snprintf(buf, sizeof(buf), "%X", static_cast<uint32_t>(cp));
             return std::string(buf);
           }());
    }
    if (cp > 0x10FFFF) {
      fail("invalid_code_point", "code point above U+10FFFF");
    }
    if (cp <= 0x7F) {
      out.push_back(static_cast<char>(cp));
    } else if (cp <= 0x7FF) {
      out.push_back(static_cast<char>(0xC0 | (cp >> 6)));
      out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    } else if (cp <= 0xFFFF) {
      out.push_back(static_cast<char>(0xE0 | (cp >> 12)));
      out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
      out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    } else {
      out.push_back(static_cast<char>(0xF0 | (cp >> 18)));
      out.push_back(static_cast<char>(0x80 | ((cp >> 12) & 0x3F)));
      out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
      out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    }
  }
  return out;
}

std::size_t utf8_length(std::string_view text) { return utf8_decode(text).size(); }

}  // namespace legal_git
