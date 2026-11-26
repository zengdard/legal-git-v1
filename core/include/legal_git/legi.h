#pragma once

#include <nlohmann/json.hpp>
#include <string>
#include <string_view>

#include "legal_git/common.h"

namespace legal_git {

// LEGI / DILA open data fiche parsers (open data LEGI distribution,
// echanges.dila.gouv.fr/OPENDATA/LEGI, licence ouverte v2.0).
//
// Three fiche kinds are parsed into neutral JSON, prior to canonical
// mapping. Field names stay close to the LEGI XML for traceability.
//
// - parse_legi_article : <ARTICLE> fiches (one immutable version of a
//   logical article; META_ARTICLE dates, VERSIONS continuity evidence,
//   CONTEXTE placement chain, BLOC_TEXTUEL content, LIENS).
// - parse_legi_section : <SECTION_TA> fiches (structure: ordered children
//   section/article links).
// - parse_legi_struct : <TEXTELR> root fiches (top structure of a texte).
//
// Content is preserved as the exact *inner* XML of BLOC_TEXTUEL/CONTENU
// (after documented XML decoding); `contenu_has_markup` tells whether the
// fragment contains child elements. Throws CoreError("parse_error") on
// structural errors.

nlohmann::json parse_legi_article(std::string_view xml_bytes);
nlohmann::json parse_legi_section(std::string_view xml_bytes);
nlohmann::json parse_legi_struct(std::string_view xml_bytes);
nlohmann::json parse_legi_version(std::string_view xml_bytes);

}  // namespace legal_git
