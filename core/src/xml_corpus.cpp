#include "legal_git/xml_corpus.h"

#include <map>
#include <set>
#include <string>

#include "pugixml.hpp"

namespace legal_git {

namespace {

using nlohmann::json;

[[noreturn]] void parse_error(const std::string& what) {
  throw CoreError("parse_error", what);
}

// Converts an empty attribute value to null ("not provided by the source").
json null_if_empty(const pugi::xml_attribute& attribute) {
  if (attribute.empty() || std::string(attribute.value()).empty()) {
    return nullptr;
  }
  return std::string(attribute.value());
}

const std::map<std::string, std::string>& lien_type_mapping() {
  static const std::map<std::string, std::string> mapping = {
      {"CITATION", "cites"},   {"CITATION_TXT", "cites"},
      {"CONTEXTE", "related_to"}, {"ABROGATION", "repeals"},
      {"MODIFICATION", "amends"},  {"CREATION", "related_to"},
  };
  return mapping;
}

struct ParseState {
  json corpus;
  std::vector<json> nodes;
  std::vector<json> versions;
  std::vector<json> relationships;
  std::vector<json> unsupported;
  std::set<std::string> seen_upstream_ids;
};

void record_unsupported(ParseState& state, const std::string& where,
                        const pugi::xml_node& node) {
  json entry;
  entry["where"] = where;
  entry["element"] = std::string(node.name());
  state.unsupported.push_back(std::move(entry));
}

void parse_liens(ParseState& state, const std::string& node_upstream_id,
                 const pugi::xml_node& article) {
  for (pugi::xml_node child : article.children("lien")) {
    const auto type_attr = child.attribute("type");
    const auto target_attr = child.attribute("target");
    if (type_attr.empty() || target_attr.empty()) {
      parse_error("article '" + node_upstream_id +
                  "' has a <lien> without 'type' or 'target'");
    }
    const std::string upstream_type = type_attr.value();
    auto it = lien_type_mapping().find(upstream_type);
    json rel;
    rel["from_node_upstream_id"] = node_upstream_id;
    rel["upstream_type"] = upstream_type;
    rel["relationship_type"] =
        it != lien_type_mapping().end() ? it->second : "related_to";
    if (it == lien_type_mapping().end()) {
      json meta;
      meta["note"] = "unknown upstream lien type; mapped to related_to";
      rel["metadata"] = meta;
    }
    rel["target_upstream_id"] = std::string(target_attr.value());
    rel["description"] = null_if_empty(child.attribute("description"));
    state.relationships.push_back(std::move(rel));
  }
  for (pugi::xml_node child : article.children()) {
    const std::string name = child.name();
    if (name != "lien" && name != "text" && !name.empty()) {
      record_unsupported(state, "article " + node_upstream_id, child);
    }
  }
}

json parse_article_text(ParseState& state, const std::string& node_upstream_id,
                        const pugi::xml_node& article) {
  bool seen = false;
  json content;
  for (pugi::xml_node child : article.children("text")) {
    if (seen) {
      parse_error("article '" + node_upstream_id +
                  "' has more than one <text> element");
    }
    seen = true;
    const pugi::xml_node pcdata = child.first_child();
    std::string bytes;
    if (!pcdata.empty() && pcdata.type() != pugi::node_pcdata &&
        pcdata.type() != pugi::node_cdata) {
      record_unsupported(state, "article " + node_upstream_id + " <text>", child);
    }
    for (pugi::xml_node piece : child.children()) {
      if (piece.type() == pugi::node_pcdata || piece.type() == pugi::node_cdata) {
        bytes.append(piece.value());
      } else {
        parse_error("article '" + node_upstream_id +
                    "' has structured content inside <text>");
      }
    }
    content = bytes;
  }
  if (!seen) {
    parse_error("article '" + node_upstream_id + "' has no <text> element");
  }
  return content;
}

void parse_article(ParseState& state, const json& corpus, json node,
                   const pugi::xml_node& article,
                   const std::string& parent_upstream_id, int order, int depth) {
  const auto id_attr = article.attribute("id");
  const auto num_attr = article.attribute("num");
  if (id_attr.empty() || id_attr.value()[0] == '\0') {
    parse_error("article without 'id' attribute");
  }
  const std::string upstream_id = id_attr.value();
  if (state.seen_upstream_ids.count(upstream_id) != 0) {
    parse_error("duplicate node upstream id '" + upstream_id + "'");
  }
  state.seen_upstream_ids.insert(upstream_id);
  if (num_attr.empty() || num_attr.value()[0] == '\0') {
    parse_error("article '" + upstream_id + "' without 'num' attribute");
  }

  node["upstream_id"] = upstream_id;
  node["node_type"] = "article";
  node["num"] = std::string(num_attr.value());
  node["label"] = null_if_empty(article.attribute("label"));
  if (node["label"].is_null()) {
    node["label"] = "Article " + std::string(num_attr.value());
  }
  node["title"] = nullptr;
  node["upstream_parent_id"] =
      parent_upstream_id.empty() ? json(nullptr) : json(parent_upstream_id);
  node["order"] = order;
  node["depth"] = depth;

  json node_metadata = json::object();
  if (!article.attribute("demo-only").empty() &&
      std::string(article.attribute("demo-only").value()) == "true") {
    node_metadata["demo_only"] = true;
  }
  node["metadata"] = node_metadata;
  state.nodes.push_back(node);

  json version;
  version["node_upstream_id"] = upstream_id;
  version["upstream_version_id"] =
      null_if_empty(article.attribute("version-id"));
  version["content"] = parse_article_text(state, upstream_id, article);
  version["content_format"] = "plain_text";
  version["valid_from"] = null_if_empty(article.attribute("valid-from"));
  version["valid_to"] = null_if_empty(article.attribute("valid-to"));
  version["published_at"] = null_if_empty(article.attribute("published-at"));
  version["effective_from"] =
      null_if_empty(article.attribute("effective-from"));
  version["effective_to"] = null_if_empty(article.attribute("effective-to"));
  version["state"] = null_if_empty(article.attribute("state"));
  json version_metadata = json::object();
  if (!article.attribute("demo-only").empty() &&
      std::string(article.attribute("demo-only").value()) == "true") {
    version_metadata["demo_only"] = true;
  }
  version["metadata"] = version_metadata;
  state.versions.push_back(std::move(version));

  parse_liens(state, upstream_id, article);
}

void parse_division(ParseState& state, const json& corpus, json node,
                    const pugi::xml_node& division,
                    const std::string& parent_upstream_id, int order,
                    int depth) {
  const auto id_attr = division.attribute("id");
  const auto type_attr = division.attribute("type");
  if (id_attr.empty() || id_attr.value()[0] == '\0') {
    parse_error("<division> without 'id' attribute");
  }
  if (type_attr.empty() || type_attr.value()[0] == '\0') {
    parse_error("<division> '" + std::string(id_attr.value()) +
                "' without 'type' attribute");
  }
  const std::string upstream_id = id_attr.value();
  if (state.seen_upstream_ids.count(upstream_id) != 0) {
    parse_error("duplicate node upstream id '" + upstream_id + "'");
  }
  state.seen_upstream_ids.insert(upstream_id);

  std::string label;
  const auto label_attr = division.attribute("label");
  if (!label_attr.empty() && label_attr.value()[0] != '\0') {
    label = label_attr.value();
  } else {
    const auto num_attr = division.attribute("num");
    label = std::string(type_attr.value());
    if (!num_attr.empty() && num_attr.value()[0] != '\0') {
      label += " " + std::string(num_attr.value());
    }
  }

  node["upstream_id"] = upstream_id;
  node["node_type"] = std::string(type_attr.value());
  node["num"] = null_if_empty(division.attribute("num"));
  node["label"] = label;
  node["title"] = null_if_empty(division.attribute("title"));
  node["upstream_parent_id"] =
      parent_upstream_id.empty() ? json(nullptr) : json(parent_upstream_id);
  node["order"] = order;
  node["depth"] = depth;
  node["metadata"] = json::object();
  state.nodes.push_back(node);

  int child_order = 0;
  for (pugi::xml_node child : division.children()) {
    const std::string name = child.name();
    if (name == "division") {
      parse_division(state, corpus, node, child, upstream_id, child_order++,
                    depth + 1);
    } else if (name == "article") {
      parse_article(state, corpus, node, child, upstream_id, child_order++,
                    depth + 1);
    } else if (!name.empty()) {
      record_unsupported(state, "division " + upstream_id, child);
    }
  }
}

}  // namespace

nlohmann::json parse_corpus_xml(std::string_view xml_bytes) {
  pugi::xml_document document;
  // parse_cdata | parse_escapes: decode XML entities and CDATA but otherwise
  // keep text nodes exactly as in the source document (no newline folding).
  const unsigned flags = pugi::parse_cdata | pugi::parse_escapes;
  const pugi::xml_parse_result result = document.load_buffer(
      xml_bytes.data(), xml_bytes.size(), flags, pugi::encoding_utf8);
  if (!result) {
    parse_error("XML parsing failed: " + std::string(result.description()));
  }

  const pugi::xml_node root = document.document_element();
  if (root == nullptr || std::string(root.name()) != "legal-git-corpus") {
    parse_error("missing <legal-git-corpus> root element");
  }

  ParseState state;
  json& corpus = state.corpus;
  const auto required = [&](const char* name) {
    const auto attribute = root.attribute(name);
    if (attribute.empty() || attribute.value()[0] == '\0') {
      parse_error(std::string("corpus root is missing required attribute '") +
                  name + "'");
    }
    return std::string(attribute.value());
  };
  corpus["jurisdiction"] = required("jurisdiction");
  corpus["slug"] = required("slug");
  corpus["title"] = required("title");
  corpus["release_id"] = required("release-id");
  std::string evidence = required("evidence");
  if (evidence != "official" && evidence != "fixture") {
    parse_error("corpus 'evidence' must be 'official' or 'fixture', got '" +
                evidence + "'");
  }
  corpus["evidence"] = evidence;
  corpus["document_type"] = null_if_empty(root.attribute("document-type"));
  if (corpus["document_type"].is_null()) {
    corpus["document_type"] = "code";
  }
  corpus["official_id"] = null_if_empty(root.attribute("official-id"));

  json node_template = json::object();
  int order = 0;
  for (pugi::xml_node child : root.children()) {
    const std::string name = child.name();
    if (name == "division") {
      parse_division(state, corpus, node_template, child, "", order++, 0);
    } else if (!name.empty() && name != "metadata") {
      record_unsupported(state, "corpus", child);
    }
  }
  if (state.nodes.empty()) {
    parse_error("corpus contains no structural nodes");
  }
  if (root.child("metadata") != nullptr) {
    for (pugi::xml_node meta : root.child("metadata").children()) {
      if (std::string(meta.name()).empty()) {
        continue;
      }
      record_unsupported(state, "corpus metadata", meta);
    }
  }

  nlohmann::json output;
  output["corpus"] = corpus;
  output["nodes"] = state.nodes;
  output["versions"] = state.versions;
  output["relationships"] = state.relationships;
  output["unsupported"] = state.unsupported;
  return output;
}

}  // namespace legal_git
