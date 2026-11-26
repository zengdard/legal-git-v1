#include "legal_git/fragment.h"

#include <string>

#include "legal_git/utf8.h"

namespace legal_git {

FragmentData extract_fragment(std::string_view content,
                              std::uint64_t start,
                              std::uint64_t end,
                              std::string_view offset_unit) {
  if (offset_unit != "unicode_code_point") {
    throw CoreError("invalid_offset_unit",
                    "unsupported offset unit '" + std::string(offset_unit) +
                        "'; V1 supports 'unicode_code_point'");
  }
  if (start > end) {
    throw CoreError("invalid_range",
                    "start offset (" + std::to_string(start) +
                        ") is greater than end offset (" + std::to_string(end) +
                        ")");
  }

  // Content must decode; checked here so that offsets are always computed
  // against a validated exact representation.
  const std::u32string code_points = utf8_decode(content);
  if (end > static_cast<std::uint64_t>(code_points.size())) {
    throw CoreError("invalid_range",
                    "end offset (" + std::to_string(end) +
                        ") exceeds the content length (" +
                        std::to_string(code_points.size()) +
                        " code points)");
  }

  FragmentData data;
  data.text = utf8_encode(std::u32string_view(code_points)
                              .substr(static_cast<std::size_t>(start),
                                      static_cast<std::size_t>(end - start)));
  data.start = start;
  data.end = end;
  data.offset_unit = std::string(offset_unit);
  data.content_length = code_points.size();
  return data;
}

}  // namespace legal_git
