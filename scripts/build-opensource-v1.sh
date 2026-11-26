#!/usr/bin/env bash
# Builds the open-source V1 engine (legal-git-v1) into dist/legal-git-v1.
#
# Scope: the V1 SYSTEM ONLY — canonical model, immutable versioning,
# ingestion (corpus fixture + LEGI + Legilux), exact diffs, fragments,
# V1 REST API, exports, metrics. Excluded: the V2 semantic layer, the web
# console (accounts, Google sign-in), the MCP server — these remain in
# the hosted product repository.
#
# The result is a self-contained tree with its own git history.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$REPO_ROOT/dist/legal-git-v1"

rm -rf "$DIST"
mkdir -p "$DIST"

# ------------------------------------------------------------------ copy V1
rsync -a --exclude '.git' --exclude '.venv' --exclude 'var/' \
      --exclude 'core/build' --exclude '__pycache__' --exclude 'dist' \
      --exclude '.pytest_cache' --exclude '*.so' \
      "$REPO_ROOT/" "$DIST/"

# -------------------------------------------------------- strip V2 / product
rm -rf "$DIST/app/v2"
rm -rf "$DIST/oss"
rm -rf "$DIST/legal_git.egg-info"
rm -rf "$DIST/examples"
rm -rf "$DIST/app/web"
rm -rf "$DIST/app/auth"
rm -rf "$DIST/docs/v2.md" "$DIST/docs/cssf-feasibility.md" \
       "$DIST/docs/legilux-feasibility.md"
rm -f  "$DIST/app/mcp_server.py" \
       "$DIST/app/api/routes_v2.py" "$DIST/app/api/deps_v2.py" \
       "$DIST/core/src/v2_semantic.cpp" \
       "$DIST/core/include/legal_git/v2_semantic.h" \
       "$DIST/core/tests/test_v2_semantic.cpp" "$DIST/core/tests/test_v2_improved.cpp" \
       "$DIST/migrations/versions/0003_v2_semantic_layer.py" \
       "$DIST/migrations/versions/0004_web_accounts.py" \
       "$DIST/migrations/versions/0005_google_identity.py" \
       "$DIST/tests/conftest_v2_backup.py"

rm -f "$DIST"/tests/integration/test_v2_*.py \
      "$DIST"/tests/integration/test_web*.py \
      "$DIST"/tests/integration/test_mcp_server.py \
      "$DIST"/tests/integration/test_legilux_adapter.py \
      "$DIST"/tests/unit/test_v2_logging.py

python3 - "$DIST" <<'PYEOF'
import pathlib
import re
import sys

dist = pathlib.Path(sys.argv[1])

def patch(path, old, new, count=1):
    p = dist / path
    s = p.read_text()
    if old not in s:
        raise SystemExit(f"patch miss in {path}: {old[:60]!r}")
    p.write_text(s.replace(old, new, count))

# ── main.py: V1 API only (no V2 router, no web console) ────────────────────
patch("app/main.py",
      """from app.api import (
    routes_documents,
    routes_exports,
    routes_nodes,
    routes_sources,
    routes_v2,
)""",
      """from app.api import (
    routes_documents,
    routes_exports,
    routes_nodes,
    routes_sources,
)""")
main = (dist / "app/main.py").read_text()
main = main.replace("from app.web import router as web_router\n", "")
main = main.replace("    app.include_router(routes_v2.router)\n", "")
main = re.sub(
    r"\n    # Landing page.*?app\.include_router\(web_router\)\n",
    "\n",
    main, flags=re.S)
(dist / "app/main.py").write_text(main)

# ── pybind: V1 core only (no V2 extractors) ───────────────────────────────
module_path = dist / "core/pybind/module.cpp"
module = module_path.read_text()

def drop_def(text, name):
    """Removes the complete m.def( ... ) call binding `name`, using
    parenthesis matching (docstrings may span several lines)."""
    marker = f'"{name}"'
    pos = text.find(marker)
    if pos < 0:
        raise SystemExit(f"binding {name} not found")
    start = text.rfind("m.def(", 0, pos)
    if start < 0:
        raise SystemExit(f"m.def( before {name} not found")
    depth = 0
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    end = i + 1
    if text[end:end + 1] == ";":
        end += 1
    return text[:start] + text[end:]

module = drop_def(module, "extract_references")
module = drop_def(module, "analyze_syntax")
module = module.replace('#include "legal_git/v2_semantic.h"\n', "")
module_path.write_text(module)

# ── config.py: V1 engine settings only (V2/console/OAuth stripped) ───────
cfg = (dist / "app/config.py").read_text()
cfg = re.sub(
    r"\n    # V2 reviewer/admin API keys:.*?v2_api_keys: str = \"\"\n",
    "\n", cfg, flags=re.S)
cfg = re.sub(
    r"\n    # Web console .*?google_redirect_base: str = \"https://app\.hypetf\.com\"\n",
    "\n", cfg, flags=re.S)
(dist / "app/config.py").write_text(cfg)

# ── app/core.py: no V2 native re-exports ──────────────────────────────────
core_py = dist / "app/core.py"
s_core = core_py.read_text()
s_core = s_core.replace("extract_references = _core.extract_references\n", "")
s_core = s_core.replace("analyze_syntax = _core.analyze_syntax\n", "")
core_py.write_text(s_core)

# ── CMakeLists: no V2 sources/tests ────────────────────────────────────────
cml = (dist / "core/CMakeLists.txt").read_text()
cml = cml.replace("  src/v2_semantic.cpp\n", "")
cml = cml.replace("    tests/test_v2_semantic.cpp\n", "")
cml = cml.replace("    tests/test_v2_improved.cpp\n", "")
(dist / "core/CMakeLists.txt").write_text(cml)

# ── pyproject: the engine only (no MCP dependency) ─────────────────────────
proj = (dist / "pyproject.toml").read_text()
proj = proj.replace('  "mcp>=2.0",\n', "")
proj = proj.replace(
    'name = "legal-git"\nversion = "0.1.0"',
    'name = "legal-git"\nversion = "1.0.0"')
proj = proj.replace(
    'description = "Structured, hierarchical, versioned legal-document data layer for developers."',
    'description = "Versioned legal-document engine: immutable versions, exact diffs, faithful hierarchy, REST API. Self-hostable for contracts, T&Cs and regulatory texts."')
(dist / "pyproject.toml").write_text(proj)

# ── conftest: V1 test bootstrap only ──────────────────────────────────────
conftest = (dist / "tests/conftest.py").read_text()
conftest = conftest.replace(
    'os.environ.setdefault(\n    "LEGALGIT_V2_API_KEYS", "rev-test=reviewer;adm-test=admin"\n)\n', "")
conftest = conftest.replace("import app.v2.models  # noqa: F401,E402\n", "")
conftest = conftest.replace(
    "import app.auth.service  # noqa: F401,E402  (users table)\n", "")
(dist / "tests/conftest.py").write_text(conftest)

# ── compose: database + api only (the V2 worker is a product feature) ─────
for name in ("compose.yaml", "docker-compose.yml"):
    compose = dist / name
    if compose.exists():
        c = compose.read_text()
        c = re.sub(r"\n  worker:.*?(?=\n  [a-z]|\Z)", "\n", c, flags=re.S)
        compose.write_text(c)
print("patches applied")
PYEOF

# sanity: the only app.v2 references left must be inside try/except
# ImportError guards (V1 builds run without the V2 package at all).
if grep -rn "routes_v2\|web_router" "$DIST/app" "$DIST/core/CMakeLists.txt" 2>/dev/null; then
  echo "!! unguarded V2 references left in the dist"; exit 1
fi
python3 - "$DIST" <<'GUARD'
import pathlib, re, sys
for path in pathlib.Path(sys.argv[1], "app").rglob("*.py"):
    text = path.read_text()
    for m in re.finditer(r"from app\.v2[^\n]*", text):
        before = text[:m.start()]
        if not re.search(r"try:\s*(?:#[^\n]*)?\s*$", before):
            sys.exit(f"unguarded app.v2 import in {path}: {m.group(0)}")
GUARD

# ------------------------------------------------- open-source project files
# LICENSE / NOTICE / README / COMMERCIAL / CONTRIBUTING + the engine CI.
cp "$REPO_ROOT/oss/LICENSE"        "$DIST/LICENSE"
cp "$REPO_ROOT/oss/NOTICE"         "$DIST/NOTICE"
cp "$REPO_ROOT/oss/README.md"      "$DIST/README.md"
cp "$REPO_ROOT/oss/COMMERCIAL.md"  "$DIST/COMMERCIAL.md"
cp "$REPO_ROOT/oss/CONTRIBUTING.md" "$DIST/CONTRIBUTING.md"
mkdir -p "$DIST/.github/workflows"
cp "$REPO_ROOT/oss/.github/workflows/ci.yml" "$DIST/.github/workflows/ci.yml"

# ---------------------------------------------------------------- git history
if [ "${SKIP_GIT:-0}" != "1" ]; then
  ( cd "$DIST" \
    && git init -q -b main \
    && git add -A \
    && git -c user.name="Legal Git" -c user.email="noreply@legalgit.local" \
         commit -q -m "Legal Git v1.0.0 — versioned legal-document engine

Self-hostable engine for contracts, T&Cs and regulatory texts:
immutable versions, exact character diffs, faithful hierarchy, REST API.

Apache-2.0. Ingested data sources remain under their own licenses
(LEGI / Licence ouverte 2.0, Legilux / CC BY 4.0); official
publications remain authoritative." )
fi

echo "dist prête : $DIST"

