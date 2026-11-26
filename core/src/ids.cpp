#include "legal_git/ids.h"

#include <algorithm>
#include <cctype>
#include <string>

#include "legal_git/sha256.h"

namespace legal_git {

namespace {

[[noreturn]] void invalid(const std::string& what) {
  throw CoreError("invalid_argument", what);
}

bool is_hex_64(std::string_view value) {
  if (value.size() != 64) {
    return false;
  }
  return std::all_of(value.begin(), value.end(), [](char c) {
    return std::isdigit(static_cast<unsigned char>(c)) != 0 ||
           (c >= 'a' && c <= 'f');
  });
}

}  // namespace

std::string normalize_slug_component(std::string_view component) {
  std::string out;
  out.reserve(component.size());
  bool previous_dash = true;  // trims leading dashes
  for (char c : component) {
    const unsigned char uc = static_cast<unsigned char>(c);
    if (std::isalnum(uc) != 0) {
      out.push_back(static_cast<char>(std::tolower(uc)));
      previous_dash = false;
    } else if (!previous_dash && !out.empty()) {
      out.push_back('-');
      previous_dash = true;
    }
  }
  while (!out.empty() && out.back() == '-') {
    out.pop_back();
    previous_dash = false;
  }
  return out;
}

std::string make_document_id(std::string_view jurisdiction,
                             std::string_view slug) {
  std::string j = normalize_slug_component(jurisdiction);
  std::string s = normalize_slug_component(slug);
  if (j.empty() || s.empty()) {
    invalid("jurisdiction and slug must both be non-empty after normalization");
  }
  return "lg:" + j + ":" + s;
}

std::string make_node_id(std::string_view document_id,
                         std::string_view node_type,
                         std::string_view identifier) {
  if (document_id.size() < 3 || document_id.substr(0, 3) != "lg:") {
    invalid("document_id must be a 'lg:' document identifier, got '" +
            std::string(document_id) + "'");
  }
  std::string type = normalize_slug_component(node_type);
  std::string ident = normalize_slug_component(identifier);
  if (type.empty() || ident.empty()) {
    invalid("node_type and identifier must both be non-empty after normalization");
  }
  return std::string(document_id) + ":" + type + ":" + ident;
}

std::string version_fingerprint(std::string_view content_format,
                                std::string_view content,
                                std::string_view upstream_version_id,
                                std::string_view valid_from,
                                std::string_view valid_to,
                                std::string_view published_at,
                                std::string_view effective_from,
                                std::string_view effective_to) {
  // Deterministic serialization of the immutable source facts. Fields are
  // joined with a unit separator (U+001F never appears in these fields in
  // practice); an empty field (meaning "null / not provided") is written as
  // an explicit sentinel so that null and an eventual empty-string value
  // never collide.
  constexpr char kSep = '\x1F';
  constexpr char kNull = '\x1E';

  std::string canonical;
  auto add = [&](std::string_view value) {
    if (!canonical.empty()) {
      canonical.push_back(kSep);
    }
    if (value.empty()) {
      canonical.push_back(kNull);
    } else {
      canonical.append(value);
    }
  };

  add(content_format);
  add(content);
  add(upstream_version_id);
  add(valid_from);
  add(valid_to);
  add(published_at);
  add(effective_from);
  add(effective_to);

  return sha256_hex(canonical);
}

std::string make_version_id(std::string_view node_id,
                            std::string_view fingerprint) {
  if (node_id.size() < 3 || node_id.substr(0, 3) != "lg:") {
    invalid("node_id must be a 'lg:' node identifier, got '" +
            std::string(node_id) + "'");
  }
  if (!is_hex_64(fingerprint)) {
    invalid("fingerprint must be a 64-char lowercase hex sha256 value");
  }
  return "lgv:" + std::string(node_id.substr(3)) + ":" +
         std::string(fingerprint.substr(0, 16));
}

}  // namespace legal_git
