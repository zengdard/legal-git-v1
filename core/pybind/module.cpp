// pybind11 bindings for the Legal Git core.
//
// This module is the single bridge between the FastAPI/SQLAlchemy layer and
// the C++20 document core (parsing, hashing, diffing, fragment addressing,
// identity derivation). All functions raise `legalgit_core.CoreError` with a
// `.code` attribute (stable machine-readable error code).

#include <nlohmann/json.hpp>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <memory>
#include <stdexcept>
#include <string>

#include "legal_git/diff.h"
#include "legal_git/fragment.h"
#include "legal_git/ids.h"
#include "legal_git/legi.h"
#include "legal_git/sha256.h"
#include "legal_git/utf8.h"
#include "legal_git/xml_corpus.h"

namespace py = pybind11;

namespace {

py::object json_to_py(const nlohmann::json& value) {
  switch (value.type()) {
    case nlohmann::json::value_t::null:
      return py::none();
    case nlohmann::json::value_t::boolean:
      return py::bool_(value.get<bool>());
    case nlohmann::json::value_t::number_integer:
      return py::int_(value.get<long long>());
    case nlohmann::json::value_t::number_unsigned:
      return py::int_(static_cast<long long>(value.get<unsigned long long>()));
    case nlohmann::json::value_t::number_float:
      return py::float_(value.get<double>());
    case nlohmann::json::value_t::string:
      return py::str(value.get<std::string>());
    case nlohmann::json::value_t::array: {
      py::list out;
      for (const auto& item : value) {
        out.append(json_to_py(item));
      }
      return std::move(out);
    }
    case nlohmann::json::value_t::object:
    default: {
      py::dict out;
      for (const auto& [key, item] : value.items()) {
        out[py::str(key)] = json_to_py(item);
      }
      return std::move(out);
    }
  }
}

const char* operation_name(legal_git::ChangeOperation operation) {
  switch (operation) {
    case legal_git::ChangeOperation::Insert:
      return "insert";
    case legal_git::ChangeOperation::Delete:
      return "delete";
    default:
      return "replace";
  }
}

py::dict change_to_py(const legal_git::Change& change) {
  py::dict out;
  out["operation"] = operation_name(change.operation);
  out["old_start"] = change.old_start;
  out["old_end"] = change.old_end;
  out["new_start"] = change.new_start;
  out["new_end"] = change.new_end;
  // Nullable text sides per the API contract: an insert has no old text, a
  // delete has no new text.
  out["old_text"] =
      change.operation == legal_git::ChangeOperation::Insert
          ? py::object(py::none())
          : py::object(py::str(change.old_text));
  out["new_text"] =
      change.operation == legal_git::ChangeOperation::Delete
          ? py::object(py::none())
          : py::object(py::str(change.new_text));
  return out;
}

// pybind11 v3 translators must be capture-free function pointers; the
// exception class is looked up in the already-imported module instead.
void translate_core_error(std::exception_ptr p) {
  if (!p) {
    return;
  }
  try {
    std::rethrow_exception(p);
  } catch (const legal_git::CoreError& e) {
    try {
      py::module_ module = py::module_::import("legalgit_core");
      py::object error_class = module.attr("CoreError");
      py::object instance = error_class(std::string(e.what()));
      instance.attr("code") = py::str(e.code);
      PyErr_SetObject(error_class.ptr(), instance.ptr());
    } catch (py::error_already_set&) {
      // Fall back to a plain RuntimeError if anything above failed.
      PyErr_SetString(PyExc_RuntimeError, e.what());
    }
  }
  // Other C++ exceptions fall through to pybind's default translators.
}

}  // namespace

PYBIND11_MODULE(legalgit_core, m) {
  m.doc() =
      "Legal Git document core: deterministic IDs, content hashing,\n"
      "minimal text diffs, version-scoped fragments and corpus XML parsing.\n"
      "Errors are raised as legalgit_core.CoreError with a stable .code "
      "attribute.";

  // Exception class carrying the C++ CoreError code; the capture-free
  // translator registered below fills the `code` attribute.
  py::exception<legal_git::CoreError>(m, "CoreError");
  py::register_exception_translator(&translate_core_error);

  m.def(
      "sha256_hex",
      [](const std::string& bytes) { return std::string(legal_git::sha256_hex(bytes)); },
      py::arg("data"),
      "SHA-256 of the input bytes as lowercase hex (no prefix).");

  m.def(
      "diff_text",
      [](const std::string& old_text, const std::string& new_text) {
        const legal_git::DiffResult result =
            legal_git::diff_text(old_text, new_text);
        py::dict out;
        out["algorithm"] = result.algorithm;
        out["offset_unit"] = result.offset_unit;
        py::list changes;
        for (const auto& change : result.changes) {
          changes.append(change_to_py(change));
        }
        out["changes"] = std::move(changes);
        return out;
      },
      py::arg("old_text"), py::arg("new_text"),
      "Minimal character-range diff between two exact version contents "
      "(Unicode code-point offsets, half-open ranges).");

  m.def(
      "extract_fragment",
      [](const std::string& content, std::uint64_t start, std::uint64_t end,
         const std::string& offset_unit) {
        const legal_git::FragmentData data =
            legal_git::extract_fragment(content, start, end, offset_unit);
        py::dict out;
        out["text"] = data.text;
        out["start"] = data.start;
        out["end"] = data.end;
        out["offset_unit"] = data.offset_unit;
        out["content_length"] = data.content_length;
        return out;
      },
      py::arg("content"), py::arg("start"), py::arg("end"),
      py::arg("offset_unit"),
      "Extracts [start, end) in the declared offset unit from the exact "
      "content of one node version; validates the range.");

  m.def(
      "normalize_slug_component",
      &legal_git::normalize_slug_component, py::arg("component"),
      "Normalizes one ID component (ASCII lowercase, '-'-separated).");

  m.def("make_document_id", &legal_git::make_document_id, py::arg("jurisdiction"),
        py::arg("slug"),
        "Deterministic logical document ID: 'lg:<jurisdiction>:<slug>'.");

  m.def(
      "make_node_id", &legal_git::make_node_id, py::arg("document_id"),
      py::arg("node_type"), py::arg("identifier"),
      "Deterministic logical node ID appended to a document ID. Independent "
      "of the node content.");

  m.def(
      "version_fingerprint",
      [](const std::string& content_format, const std::string& content,
         const std::string& upstream_version_id, const std::string& valid_from,
         const std::string& valid_to, const std::string& published_at,
         const std::string& effective_from, const std::string& effective_to) {
        return legal_git::version_fingerprint(
            content_format, content, upstream_version_id, valid_from, valid_to,
            published_at, effective_from, effective_to);
      },
      py::arg("content_format"), py::arg("content"),
      py::arg("upstream_version_id"), py::arg("valid_from"),
      py::arg("valid_to"), py::arg("published_at"),
      py::arg("effective_from"), py::arg("effective_to"),
      "Deterministic sha256 (64 hex) over the immutable source facts of a "
      "node version. Empty strings mean null.");

  m.def(
      "make_version_id", &legal_git::make_version_id, py::arg("node_id"),
      py::arg("fingerprint"),
      "Deterministic immutable version ID: "
      "'lgv:<node path>:<fingerprint[:16]>'.");

  m.def(
      "parse_corpus_xml",
      [](const std::string& xml_bytes) {
        return json_to_py(legal_git::parse_corpus_xml(xml_bytes));
      },
      py::arg("xml"),
      "Parses a Legal Git corpus XML package (fixture grammar) into a "
      "dict with corpus, nodes, versions, relationships and unsupported "
      "element records.");

  m.def(
      "parse_legi_article",
      [](const std::string& xml_bytes) {
        return json_to_py(legal_git::parse_legi_article(xml_bytes));
      },
      py::arg("xml"),
      "Parses a LEGI <ARTICLE> fiche (one immutable version of a logical "
      "article) into a neutral dict: dates, VERSIONS continuity evidence, "
      "CONTEXTE placement, exact BLOC_TEXTUEL content, LIENS.");

  m.def(
      "parse_legi_section",
      [](const std::string& xml_bytes) {
        return json_to_py(legal_git::parse_legi_section(xml_bytes));
      },
      py::arg("xml"),
      "Parses a LEGI <SECTION_TA> fiche: title, ordered child section and "
      "article links, CONTEXTE placement.");

  m.def(
      "parse_legi_struct",
      [](const std::string& xml_bytes) {
        return json_to_py(legal_git::parse_legi_struct(xml_bytes));
      },
      py::arg("xml"),
      "Parses a LEGI <TEXTELR> root fiche: texte identity, versions, "
      "top-level children.");

  m.def(
      "parse_legi_version",
      [](const std::string& xml_bytes) {
        return json_to_py(legal_git::parse_legi_version(xml_bytes));
      },
      py::arg("xml"),
      "Parses a LEGI <TEXTE_VERSION> fiche (title metadata of a texte).");

  m.def(
      "utf8_length", [](const std::string& text) {
        return legal_git::utf8_length(text);
      },
      py::arg("text"),
      "Number of Unicode code points in a valid UTF-8 string.");

  

  
}
