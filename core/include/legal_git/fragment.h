#pragma once

#include <cstdint>
#include <string>
#include <string_view>

#include "legal_git/common.h"

namespace legal_git {

struct FragmentData {
  std::string text;          // exact extracted text, re-encoded UTF-8
  std::uint64_t start;       // echoed validated start offset
  std::uint64_t end;         // echoed validated end offset (half-open)
  std::string offset_unit;   // echoed offset unit
  std::uint64_t content_length;  // code-point length of the version content
};

// Extracts the [start, end) range of code points from a version's exact
// content. Offsets are version-scoped by construction: the caller supplies
// the content of one specific node version.
// Throws CoreError("invalid_offset_unit") for unknown units and
// CoreError("invalid_range") when start > end or end exceeds the content,
// or CoreError("invalid_utf8") on malformed content.
FragmentData extract_fragment(std::string_view content,
                               std::uint64_t start,
                               std::uint64_t end,
                               std::string_view offset_unit);

}  // namespace legal_git
