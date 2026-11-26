#include "legal_git/legi.h"

#include <map>
#include <string>

#include "pugixml.hpp"

namespace legal_git {

namespace {

using nlohmann::json;

[[noreturn]] void parse_error(const std::string& what) {
  throw CoreError("parse_error", what);
}

json null_if_empty(const pugi::xml_attribute& attribute) {
  if (attribute.empty() || attribute.value()[0] == '\0') {
    return nullptr;
  }
  return std::string(attribute.value());
}

json text_child(const pugi::xml_node& parent, const char* name) {
  const pugi::xml_node node = parent.child(name);
  if (node == nullptr) {
    return nullptr;
  }
  // Exact pcdata (no trimming — trailing spaces are part of the source).
  const pugi::xml_node pcdata = node.first_child();
  if (pcdata == nullptr) {
    return nullptr;
  }
  return std::string(pcdata.value());
}

const pugi::xml_parse_result load(pugi::xml_document& document,
                                  std::string_view xml_bytes) {
  // No newline folding: keep text nodes as in the source document.
  return document.load_buffer(xml_bytes.data(), xml_bytes.size(),
                              pugi::parse_cdata | pugi::parse_escapes,
                              pugi::encoding_utf8);
}

// Ordered children of a TM: both LIEN_SECTION_TA and LIEN_ART entries, in
// source presentation order.
json parse_structure_children(const pugi::xml_node& structure) {
  json sections = json::array();
  json articles = json::array();
  int section_order = 0;
  for (const pugi::xml_node& child : structure.children("LIEN_SECTION_TA")) {
    json entry;
    entry["cid"] = null_if_empty(child.attribute("cid"));
    entry["id"] = null_if_empty(child.attribute("id"));
    entry["titre"] = std::string(child.child_value());
    entry["etat"] = null_if_empty(child.attribute("etat"));
    entry["debut"] = null_if_empty(child.attribute("debut"));
    entry["fin"] = null_if_empty(child.attribute("fin"));
    entry["niv"] = null_if_empty(child.attribute("niv"));
    entry["order"] = section_order++;
    sections.push_back(std::move(entry));
  }
  int article_order = 0;
  for (const pugi::xml_node& child : structure.children("LIEN_ART")) {
    json entry;
    entry["id"] = null_if_empty(child.attribute("id"));
    entry["num"] = null_if_empty(child.attribute("num"));
    entry["etat"] = null_if_empty(child.attribute("etat"));
    entry["debut"] = null_if_empty(child.attribute("debut"));
    entry["fin"] = null_if_empty(child.attribute("fin"));
    entry["origine"] = null_if_empty(child.attribute("origine"));
    entry["order"] = article_order++;
    articles.push_back(std::move(entry));
  }
  json out;
  out["sections"] = std::move(sections);
  out["articles"] = std::move(articles);
  return out;
}

// CONTEXTE: texte cid + ordered TM chain (fiche ids top->down).
json parse_contexte(const pugi::xml_node& contexte) {
  const pugi::xml_node texte = contexte.child("TEXTE");
  if (texte == nullptr) {
    parse_error("CONTEXTE without TEXTE");
  }
  json out;
  out["texte_cid"] = null_if_empty(texte.attribute("cid"));
  out["texte_nature"] = null_if_empty(texte.attribute("nature"));
  const pugi::xml_node titre_txt = texte.child("TITRE_TXT");
  out["texte_titre"] = titre_txt == nullptr
                          ? json(nullptr)
                          : json(std::string(titre_txt.child_value()));
  json tms = json::array();
  if (texte.child("TM") != nullptr) {
    for (pugi::xml_node tm = texte.child("TM"); tm != nullptr;) {
      const pugi::xml_node titre_tm = tm.child("TITRE_TM");
      if (titre_tm == nullptr) {
        break;
      }
      json entry;
      entry["id"] = null_if_empty(titre_tm.attribute("id"));
      entry["titre"] = std::string(titre_tm.child_value());
      entry["debut"] = null_if_empty(titre_tm.attribute("debut"));
      entry["fin"] = null_if_empty(titre_tm.attribute("fin"));
      tms.push_back(std::move(entry));
      tm = tm.child("TM");
    }
  }
  out["tms"] = std::move(tms);
  return out;
}

json parse_liens(const pugi::xml_node& parent) {
  json liens = json::array();
  for (const pugi::xml_node& lien : parent.children("LIEN")) {
    json entry;
    entry["typelien"] = null_if_empty(lien.attribute("typelien"));
    entry["sens"] = null_if_empty(lien.attribute("sens"));
    entry["cidtexte"] = null_if_empty(lien.attribute("cidtexte"));
    entry["id"] = null_if_empty(lien.attribute("id"));
    entry["naturetexte"] = null_if_empty(lien.attribute("naturetexte"));
    entry["num"] = null_if_empty(lien.attribute("num"));
    entry["numtexte"] = null_if_empty(lien.attribute("numtexte"));
    entry["titre"] = std::string(lien.child_value());
    liens.push_back(std::move(entry));
  }
  return liens;
}

std::string serialize_contenu(const pugi::xml_node& contenu, bool* has_markup) {
  // Exact inner serialization: raw pcdata when the content is text,
  // concatenated raw child serialization when the content is a fragment
  // of (X)HTML markup. Documented transformation: pugixml decodes XML
  // entities and CDATA; the raw artifact remains the ultimate reference.
  struct StringWriter : pugi::xml_writer {
    std::string result;
    void write(const void* data, std::size_t size) override {
      result.append(static_cast<const char*>(data), size);
    }
  };

  *has_markup = false;
  std::string out;
  for (const pugi::xml_node& child : contenu.children()) {
    if (child.type() == pugi::node_pcdata || child.type() == pugi::node_cdata) {
      out.append(child.value());
    } else if (child.type() == pugi::node_element) {
      *has_markup = true;
      StringWriter writer;
      child.print(writer, "", pugi::format_raw);
      out.append(writer.result);
    }
  }
  return out;
}

}  // namespace

nlohmann::json parse_legi_article(std::string_view xml_bytes) {
  pugi::xml_document document;
  if (!load(document, xml_bytes)) {
    parse_error("invalid XML in LEGI article fiche");
  }
  const pugi::xml_node article = document.document_element();
  if (article == nullptr || std::string(article.name()) != "ARTICLE") {
    parse_error("missing <ARTICLE> root in LEGI article fiche");
  }

  const pugi::xml_node meta_commun = article.child("META").child("META_COMMUN");
  const pugi::xml_node meta_article =
      article.child("META").child("META_SPEC").child("META_ARTICLE");
  if (meta_commun == nullptr || meta_article == nullptr) {
    parse_error("article fiche without META_COMMUN/META_ARTICLE");
  }

  json out;
  out["kind"] = "article";
  out["id"] = text_child(meta_commun, "ID");
  out["ancien_id"] = text_child(meta_commun, "ANCIEN_ID");
  out["origine"] = text_child(meta_commun, "ORIGINE");
  out["nature"] = text_child(meta_commun, "NATURE");
  out["num"] = text_child(meta_article, "NUM");
  out["etat"] = text_child(meta_article, "ETAT");
  out["date_debut"] = text_child(meta_article, "DATE_DEBUT");
  out["date_fin"] = text_child(meta_article, "DATE_FIN");
  out["type"] = text_child(meta_article, "TYPE");

  // VERSIONS/LIEN_ART: the source's own continuity evidence for the logical
  // article identity (all versions of the same logical article).
  json versions = json::array();
  for (const pugi::xml_node& version :
       article.child("VERSIONS").children("VERSION")) {
    const pugi::xml_node lien_art = version.child("LIEN_ART");
    if (lien_art == nullptr) {
      continue;
    }
    json entry;
    entry["id"] = null_if_empty(lien_art.attribute("id"));
    entry["num"] = null_if_empty(lien_art.attribute("num"));
    entry["etat"] = null_if_empty(lien_art.attribute("etat"));
    entry["debut"] = null_if_empty(lien_art.attribute("debut"));
    entry["fin"] = null_if_empty(lien_art.attribute("fin"));
    entry["origine"] = null_if_empty(lien_art.attribute("origine"));
    versions.push_back(std::move(entry));
  }
  out["versions"] = std::move(versions);

  const pugi::xml_node contexte = article.child("CONTEXTE");
  if (contexte == nullptr) {
    parse_error("article fiche without CONTEXTE");
  }
  out["contexte"] = parse_contexte(contexte);

  const pugi::xml_node bloc = article.child("BLOC_TEXTUEL");
  const pugi::xml_node contenu = bloc == nullptr ? pugi::xml_node()
                                                 : bloc.child("CONTENU");
  bool has_markup = false;
  out["contenu"] = contenu == nullptr ? json(nullptr)
                                      : json(serialize_contenu(contenu, &has_markup));
  out["contenu_has_markup"] = has_markup;
  out["contenu_format"] = "xml_fragment";

  const pugi::xml_node liens = article.child("LIENS");
  out["liens"] = liens == nullptr ? json::array() : parse_liens(liens);
  return out;
}

nlohmann::json parse_legi_section(std::string_view xml_bytes) {
  pugi::xml_document document;
  if (!load(document, xml_bytes)) {
    parse_error("invalid XML in LEGI section fiche");
  }
  const pugi::xml_node section = document.document_element();
  if (section == nullptr || std::string(section.name()) != "SECTION_TA") {
    parse_error("missing <SECTION_TA> root in LEGI section fiche");
  }

  json out;
  out["kind"] = "section";
  out["id"] = text_child(section, "ID");
  out["titre_ta"] = text_child(section, "TITRE_TA");

  const pugi::xml_node structure = section.child("STRUCTURE_TA");
  out["children"] = structure == nullptr
                        ? json({{"sections", json::array()},
                                {"articles", json::array()}})
                        : parse_structure_children(structure);

  const pugi::xml_node contexte = section.child("CONTEXTE");
  if (contexte == nullptr) {
    parse_error("section fiche without CONTEXTE");
  }
  out["contexte"] = parse_contexte(contexte);
  return out;
}

nlohmann::json parse_legi_struct(std::string_view xml_bytes) {  pugi::xml_document document;
  if (!load(document, xml_bytes)) {
    parse_error("invalid XML in LEGI TEXTELR fiche");
  }
  const pugi::xml_node textelr = document.document_element();
  if (textelr == nullptr || std::string(textelr.name()) != "TEXTELR") {
    parse_error("missing <TEXTELR> root in LEGI struct fiche");
  }

  const pugi::xml_node meta_commun = textelr.child("META").child("META_COMMUN");
  const pugi::xml_node chronicle = textelr.child("META")
                                         .child("META_SPEC")
                                         .child("META_TEXTE_CHRONICLE");
  if (meta_commun == nullptr) {
    parse_error("TEXTELR without META_COMMUN");
  }

  json out;
  out["kind"] = "struct";
  out["id"] = text_child(meta_commun, "ID");
  out["ancien_id"] = text_child(meta_commun, "ANCIEN_ID");
  out["nature"] = text_child(meta_commun, "NATURE");
  out["cid"] = chronicle == nullptr ? json(nullptr)
                                    : text_child(chronicle, "CID");
  out["derniere_modification"] =
      chronicle == nullptr ? json(nullptr)
                            : text_child(chronicle, "DERNIERE_MODIFICATION");

  // VERSIONS/LIEN_TXT: the versions of the texte itself.
  json versions = json::array();
  for (const pugi::xml_node& version :
       textelr.child("VERSIONS").children("VERSION")) {
    const pugi::xml_node lien_txt = version.child("LIEN_TXT");
    if (lien_txt == nullptr) {
      continue;
    }
    json entry;
    entry["id"] = null_if_empty(lien_txt.attribute("id"));
    entry["etat"] = null_if_empty(lien_txt.attribute("etat"));
    entry["debut"] = null_if_empty(lien_txt.attribute("debut"));
    entry["fin"] = null_if_empty(lien_txt.attribute("fin"));
    versions.push_back(std::move(entry));
  }
  out["versions_texte"] = std::move(versions);

  // The TITRE_TXT entries give the texte title(s) by period.
  const pugi::xml_node contexte = textelr.child("CONTEXTE");
  const pugi::xml_node titres =
      contexte == nullptr ? pugi::xml_node() : contexte.child("TEXTE");
  if (titres != nullptr) {
    json liens = json::array();
    for (const pugi::xml_node& titre_txt : titres.children("TITRE_TXT")) {
      json entry;
      entry["titre_court"] = null_if_empty(titre_txt.attribute("c_titre_court"));
      entry["titre"] = std::string(titre_txt.child_value());
      entry["debut"] = null_if_empty(titre_txt.attribute("debut"));
      entry["fin"] = null_if_empty(titre_txt.attribute("fin"));
      liens.push_back(std::move(entry));
    }
    out["titres"] = std::move(liens);
    out["cid"] = null_if_empty(titres.attribute("cid")).is_null()
                     ? out["cid"]
                     : null_if_empty(titres.attribute("cid"));
  }

  const pugi::xml_node structure = textelr.child("STRUCT");
  out["children"] = structure == nullptr
                        ? json({{"sections", json::array()},
                                {"articles", json::array()}})
                        : parse_structure_children(structure);
  return out;
}

nlohmann::json parse_legi_version(std::string_view xml_bytes) {
  // <TEXTE_VERSION> fiche: metadata of one texte (e.g. the title of a code).
  pugi::xml_document document;
  if (!load(document, xml_bytes)) {
    parse_error("invalid XML in LEGI TEXTE_VERSION fiche");
  }
  const pugi::xml_node texte_version = document.document_element();
  if (texte_version == nullptr ||
      std::string(texte_version.name()) != "TEXTE_VERSION") {
    parse_error("missing <TEXTE_VERSION> root in LEGI version fiche");
  }
  const pugi::xml_node meta_commun = texte_version.child("META").child("META_COMMUN");
  const pugi::xml_node meta_version = texte_version.child("META")
                                            .child("META_SPEC")
                                            .child("META_TEXTE_VERSION");
  if (meta_commun == nullptr || meta_version == nullptr) {
    parse_error("TEXTE_VERSION without META_COMMUN/META_TEXTE_VERSION");
  }
  json out;
  out["kind"] = "texte_version";
  out["id"] = text_child(meta_commun, "ID");
  out["nature"] = text_child(meta_commun, "NATURE");
  out["titre"] = text_child(meta_version, "TITRE");
  out["titrefull"] = text_child(meta_version, "TITREFULL");
  return out;
}

}  // namespace legal_git
