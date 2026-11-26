#pragma once

#include <nlohmann/json.hpp>
#include <string>
#include <string_view>

#include "legal_git/common.h"

namespace legal_git {

// Parses a Legal Git fixture corpus package (XML) into a neutral JSON
// document, prior to any canonical mapping. The grammar is documented in
// docs/source_format.md:
//
//   <legal-git-corpus jurisdiction slug title release-id evidence ...>
//     <division type id num label title ...>     (recursive structure)
//       <article id num state version-id valid-from ... >
//         <text>exact text</text>
//         <lien type target description/>
//       </article>
//     </division>
//     ...
//   </legal-git-corpus>
//
// The parser preserves text byte-for-byte (after XML decoding, which is the
// documented transformation) and records unknown elements instead of
// silently dropping them.
// Throws CoreError("parse_error") on structural errors.
nlohmann::json parse_corpus_xml(std::string_view xml_bytes);

}  // namespace legal_git
