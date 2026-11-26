#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "legal_git/common.h"

namespace legal_git {

enum class ChangeOperation { Insert, Delete, Replace };

// One changed region. Ranges are half-open [start, end) expressed in Unicode
// code points, relative to the compared version contents respectively:
//  - insert: old_start == old_end == position in the old text where the new
//    text was inserted; new range covers the inserted text; old_text is empty.
//  - delete: new_start == new_end == position in the new text; old range
//    covers the removed text; new_text is empty.
//  - replace: both ranges cover the old and new text of the changed region.
struct Change {
  ChangeOperation operation;
  std::uint64_t old_start;
  std::uint64_t old_end;
  std::uint64_t new_start;
  std::uint64_t new_end;
  std::string old_text;
  std::string new_text;
};

struct DiffResult {
  std::string algorithm;    // "character-range-diff-v1"
  std::string offset_unit;  // "unicode_code_point"
  std::vector<Change> changes;
};

// Minimal edit-script diff between two exact version contents.
// Throws CoreError("invalid_utf8") on malformed input and
// CoreError("diff_too_large") when the inputs exceed the documented size cap.
DiffResult diff_text(std::string_view old_text, std::string_view new_text);

}  // namespace legal_git
