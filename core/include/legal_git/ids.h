#pragma once

#include <string>
#include <string_view>

#include "legal_git/common.h"

namespace legal_git {

// Normalizes one component of a path-style ID: ASCII-lowercase, non
// alphanumeric characters collapse to "-", edges trimmed. Non-ASCII
// characters are mapped to "-" (they must not appear in identifiers).
std::string normalize_slug_component(std::string_view component);

// "lg:<jurisdiction>:<slug>", e.g. "lg:fr:code-civil".
std::string make_document_id(std::string_view jurisdiction, std::string_view slug);

// "<document_id>:<node_type>:<identifier>",
// e.g. "lg:fr:code-civil:article:1103". Both components are normalized.
// Throws CoreError("invalid_argument") if document_id is not a "lg:" ID.
std::string make_node_id(std::string_view document_id,
                         std::string_view node_type,
                         std::string_view identifier);

// Deterministic fingerprint (sha256, 64 lowercase hex chars) of the
// immutable source facts of one node version. Empty strings mean "null /
// not provided by the source" (unambiguous for these fixed-format fields).
// Content is hashed as-is: the text of the version is part of its identity,
// unlike logical node identity which must never derive from content.
std::string version_fingerprint(std::string_view content_format,
                                std::string_view content,
                                std::string_view upstream_version_id,
                                std::string_view valid_from,
                                std::string_view valid_to,
                                std::string_view published_at,
                                std::string_view effective_from,
                                std::string_view effective_to);

// "lgv:<node path>:<fingerprint[:16]>",
// e.g. "lgv:fr:code-civil:article:1103:6f3a9c2b11d04e77".
// Throws CoreError("invalid_argument") if node_id is not a "lg:" ID or the
// fingerprint is not a 64-char hex string.
std::string make_version_id(std::string_view node_id, std::string_view fingerprint);

}  // namespace legal_git
