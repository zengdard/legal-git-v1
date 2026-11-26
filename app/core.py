"""Bridge to the C++ document core (legalgit_core pybind11 module).

The compiled module lives next to the `app` package (built by
`scripts/build_core.sh`). All functions raise `CoreError` with a stable
`.code` attribute.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PACKAGE_DIR = Path(__file__).resolve().parent
if str(_PACKAGE_DIR) not in sys.path:
    # The native .so sits in app/ next to this package.
    sys.path.insert(0, str(_PACKAGE_DIR))

import legalgit_core as _core

CoreError = _core.CoreError

diff_text = _core.diff_text
extract_fragment = _core.extract_fragment
make_document_id = _core.make_document_id
make_node_id = _core.make_node_id
make_version_id = _core.make_version_id
normalize_slug_component = _core.normalize_slug_component
parse_corpus_xml = _core.parse_corpus_xml
parse_legi_article = _core.parse_legi_article
parse_legi_section = _core.parse_legi_section
parse_legi_struct = _core.parse_legi_struct
parse_legi_version = _core.parse_legi_version
sha256_hex = _core.sha256_hex
utf8_length = _core.utf8_length
version_fingerprint = _core.version_fingerprint


def fingerprint_of_version(
    *,
    content_format: str,
    content: str,
    upstream_version_id: str | None,
    valid_from: str | None,
    valid_to: str | None,
    published_at: str | None,
    effective_from: str | None,
    effective_to: str | None,
) -> str:
    """Version fingerprint with explicit None -> empty-string mapping."""
    return version_fingerprint(
        content_format,
        content,
        upstream_version_id or "",
        valid_from or "",
        valid_to or "",
        published_at or "",
        effective_from or "",
        effective_to or "",
    )


def ensure_native_module() -> dict[str, Any]:
    """Sanity check used by the readiness endpoint and the CLI."""
    return {
        "module": "legalgit_core",
        "sha256_selftest": _core.sha256_hex("legal-git"),
    }
