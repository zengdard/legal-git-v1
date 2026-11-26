#!/usr/bin/env bash
# Backup: canonical database + object storage (raw artifacts, exports).
#
# Usage: scripts/backup.sh [backup_dir]
#   - PostgreSQL (compose): pg_dump from the db container.
#   - SQLite: VACUUM INTO (consistent copy).
#   - Object storage: tar of the storage directory (raw source artifacts).
#
# Output: var/backups/<timestamp>/{db.*, storage.tar.gz, manifest.txt}
set -euo pipefail
cd "$(dirname "$0")/.."

STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="${1:-var/backups/$STAMP}"
mkdir -p "$DEST"

DB_URL="${LEGALGIT_DATABASE_URL:-}"
if [ -z "$DB_URL" ]; then
  # fallback to the application default (sqlite var/dev.db)
  DB_URL="sqlite:///$PWD/var/dev.db"
fi

STORAGE_DIR="${LEGALGIT_STORAGE_DIR:-$PWD/var/storage}"

if [[ "$DB_URL" == postgresql* ]]; then
  # parse postgresql+pg8000://user:pass@host[:port]/db — compose defaults
  DB_HOST="$(echo "$DB_URL" | sed -E 's#.*@([^:/]+).*#\1#')"
  DB_PORT="$(echo "$DB_URL" | sed -nE 's#.*@[^:/]+:([0-9]+).*#\1#p')"
  DB_PORT="${DB_PORT:-5432}"
  DB_NAME="$(echo "$DB_URL" | sed -E 's#.*/([^/?]+).*#\1#')"
  DB_CONTAINER="${PG_CONTAINER:-legal-git_db_1}"
  podman exec "$DB_CONTAINER" pg_dump -U legalgit -d "$DB_NAME" \
    | gzip > "$DEST/db.sql.gz"
  DB_KIND="postgresql"
else
  DB_FILE="${DB_URL#sqlite:///}"
  if [ ! -f "$DB_FILE" ]; then
    echo "database file not found: $DB_FILE" >&2
    exit 1
  fi
  .venv/bin/python - "$DB_FILE" "$DEST/db.sqlite" <<'EOF'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
connection = sqlite3.connect(src)
connection.execute(f"VACUUM INTO '{dst}'")
connection.close()
print(f"backup sqlite: {dst}")
EOF
  DB_KIND="sqlite"
fi

if [ -d "$STORAGE_DIR" ]; then
  tar czf "$DEST/storage.tar.gz" -C "$(dirname "$STORAGE_DIR")" \
    "$(basename "$STORAGE_DIR")"
fi

{
  echo "timestamp: $STAMP"
  echo "db_kind: $DB_KIND"
  echo "db_url: $DB_URL"
  sha256sum "$DEST"/* 2>/dev/null || true
} > "$DEST/manifest.txt"

echo "backup completed: $DEST"
cat "$DEST/manifest.txt"
