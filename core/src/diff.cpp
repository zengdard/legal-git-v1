#include "legal_git/diff.h"

#include <cstdint>
#include <vector>

#include "legal_git/utf8.h"

namespace legal_git {

namespace {

// Guard against pathological inputs in V1: the dynamic-programming LCS table
// holds (N+1)*(M+1) uint32 cells. Documented in docs/diff.md. Text diffs are
// node-version scoped (article-sized); larger inputs are rejected loudly
// instead of exhausting memory. Raise the cap with a linear-space
// implementation if real corpus sizes demand it.
constexpr std::uint64_t kMaxCells = 16'000'000;

[[noreturn]] void fail(std::string code, const std::string& what) {
  throw CoreError(std::move(code), what);
}

enum class OpKind { Equal, Delete, Insert };

struct Op {
  OpKind kind;
};

}  // namespace

DiffResult diff_text(std::string_view old_text, std::string_view new_text) {
  const std::u32string a = utf8_decode(old_text);
  const std::u32string b = utf8_decode(new_text);
  const std::size_t n = a.size();
  const std::size_t m = b.size();

  if ((static_cast<std::uint64_t>(n) + 1) * (static_cast<std::uint64_t>(m) + 1) >
      kMaxCells) {
    fail("diff_too_large",
         "combined version sizes exceed the V1 diff cap (" +
             std::to_string(n) + " and " + std::to_string(m) +
             " code points); compare smaller node versions");
  }

  // dp[i][j] = LCS length of a[i:] and b[j:], flat array of (n+1)*(m+1).
  const std::size_t row = m + 1;
  std::vector<std::uint32_t> dp((n + 1) * row, 0);
  auto at = [&](std::size_t i, std::size_t j) -> std::uint32_t& {
    return dp[i * row + j];
  };
  for (std::size_t i = n; i-- > 0;) {
    for (std::size_t j = m; j-- > 0;) {
      if (a[i] == b[j]) {
        at(i, j) = at(i + 1, j + 1) + 1;
      } else {
        at(i, j) = std::max(at(i + 1, j), at(i, j + 1));
      }
    }
  }

  // Minimal edit script (insert/delete covers Myers' model; equal runs join
  // the gaps). Greedy walk over the LCS table is minimal by construction.
  std::vector<Op> script;
  script.reserve(n + m);
  std::size_t i = 0;
  std::size_t j = 0;
  while (i < n || j < m) {
    if (i < n && j < m && a[i] == b[j]) {
      script.push_back({OpKind::Equal});
      ++i;
      ++j;
    } else if (j < m && (i == n || at(i, j + 1) >= at(i + 1, j))) {
      // Insert (consume b[j]) when it keeps an optimal path alive; the
      // remaining LCS after an insert is dp[i][j+1].
      script.push_back({OpKind::Insert});
      ++j;
    } else {
      script.push_back({OpKind::Delete});
      ++i;
    }
  }

  // Group consecutive non-equal operations into insert/delete/replace blocks
  // with half-open code-point ranges on both sides.
  std::vector<Change> changes;
  bool open = false;
  std::size_t old_start = 0, old_end = 0;        // block range in old text
  std::size_t new_start = 0, new_end = 0;       // block range in new text
  std::size_t old_align = 0, new_align = 0;     // cursor positions at block open
  std::size_t old_pos = 0, new_pos = 0;         // cursors while replaying ops

  auto flush = [&]() {
    if (!open) {
      return;
    }
    open = false;
    if (old_start == old_end && new_start == new_end) {
      return;  // cannot happen: blocks always contain at least one op
    }
    Change change{};
    if (old_start == old_end) {
      // Pure insertion: the old position is the single point of insertion.
      change.operation = ChangeOperation::Insert;
      change.old_start = change.old_end = old_align;
      change.new_start = new_start;
      change.new_end = new_end;
      change.old_text.clear();
      change.new_text = utf8_encode(
          std::u32string_view(b).substr(new_start, new_end - new_start));
    } else if (new_start == new_end) {
      // Pure deletion: anchored at the corresponding point in the new text.
      change.operation = ChangeOperation::Delete;
      change.old_start = old_start;
      change.old_end = old_end;
      change.new_start = change.new_end = new_align;
      change.old_text = utf8_encode(
          std::u32string_view(a).substr(old_start, old_end - old_start));
      change.new_text.clear();
    } else {
      change.operation = ChangeOperation::Replace;
      change.old_start = old_start;
      change.old_end = old_end;
      change.new_start = new_start;
      change.new_end = new_end;
      change.old_text = utf8_encode(
          std::u32string_view(a).substr(old_start, old_end - old_start));
      change.new_text = utf8_encode(
          std::u32string_view(b).substr(new_start, new_end - new_start));
    }
    changes.push_back(std::move(change));
  };

  for (const Op& op : script) {
    switch (op.kind) {
      case OpKind::Delete:
        if (!open) {
          open = true;
          old_start = old_end = old_pos;
          new_start = new_end = new_pos;
          old_align = old_pos;
          new_align = new_pos;
        }
        ++old_pos;
        ++old_end;
        break;
      case OpKind::Insert:
        if (!open) {
          open = true;
          old_start = old_end = old_pos;
          new_start = new_end = new_pos;
          old_align = old_pos;
          new_align = new_pos;
        }
        ++new_pos;
        ++new_end;
        break;
      case OpKind::Equal:
        if (open) {
          flush();
        }
        ++old_pos;
        ++new_pos;
        break;
    }
  }
  flush();

  DiffResult result;
  result.algorithm = "character-range-diff-v1";
  result.offset_unit = "unicode_code_point";
  result.changes = std::move(changes);
  return result;
}

}  // namespace legal_git
