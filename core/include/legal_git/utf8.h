#pragma once

#include <string>
#include <string_view>

#include "legal_git/common.h"

namespace legal_git {

// Decodes UTF-8 into Unicode code points. Throws CoreError("invalid_utf8")
// on malformed input (bad lead bytes, truncated sequences, overlong forms,
// surrogates, values above U+10FFFF). Text is never silently normalized.
std::u32string utf8_decode(std::string_view text);

// Encodes Unicode code points as UTF-8. Throws CoreError("invalid_code_point")
// on surrogate or out-of-range values.
std::string utf8_encode(std::u32string_view code_points);

// Number of Unicode code points in a valid UTF-8 string.
std::size_t utf8_length(std::string_view text);

}  // namespace legal_git
