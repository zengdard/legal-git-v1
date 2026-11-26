#!/usr/bin/env bash
# Restore test: verifies a backup is actually usable (Phase 6 acceptance:
# "backup and restore tested").
#
# Usage: scripts/restore_test.sh <backup_dir>
#
# Restores the backup into var/restore-test/, boots the API against it on a
# scratch port, checks /readyz plus document/version queries, then cleans
# up. Exits non-zero if any step fails.
set -euo pipefail
cd "$(dirname "$0")/.."

BACKUP="${1:?usage: restore_test.sh <backup_dir>}"
PORT="${RESTORE_TEST_PORT:-8012}"
WORK="var/restore-test"
RM_RF_DIR="$WORK"
mkdir -p "$WORK"
PG_CONTAINER="${PG_CONTAINER_LEGACY:-legal-git_restore_db}"

cleanup() {
  [ -n "${API_PID:-}" ] && kill "$API_PID" 2>/dev/null || true
  podman rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true
  rm -rf "$RM_RF_DIR"
}
trap cleanup EXIT

echo "== 1. restauration"
if [ -f "$BACKUP/db.sql.gz" ]; then
  # Restore into a throwaway PostgreSQL container.
  podman run -d --name "$PG_CONTAINER" \
    -e POSTGRES_USER=legalgit -e POSTGRES_PASSWORD=legalgit -e POSTGRES_DB=legalgit \
    docker.io/library/postgres:16-alpine >/dev/null
  sleep 6
  podman exec -i "$PG_CONTAINER" psql -U legalgit -d legalgit \
    < <(gunzip -c "$BACKUP/db.sql.gz")
  export LEGALGIT_DATABASE_URL="postgresql+pg8000://legalgit:legalgit@localhost:5433/legalgit"
  if ! podman port "$PG_CONTAINER" >/dev/null 2>&1; then
    : # publish handled at run time below if needed
  fi
  # publish the scratch DB on a free host port
  HOST_PORT="$(podman inspect -f '{{.HostConfig.PortBindings}}' "$PG_CONTAINER" | grep -o '[0-9]*' | head -1 || true)"
  if [ -z "$HOST_PORT" ]; then
    HOST_PORT=5433
    podman stop "$PG_CONTAINER" >/dev/null
    podman rm "$PG_CONTAINER" >/dev/null
    podman run -d --name "$PG_CONTAINER" -p "$HOST_PORT:5432" \
      -e POSTGRES_USER=legalgit -e POSTGRES_PASSWORD=legalgit -e POSTGRES_DB=legalgit \
      docker.io/library/postgres:16-alpine >/dev/null
    sleep 6
    podman exec -i "$PG_CONTAINER" psql -U legalgit -d legalgit \
      < <(gunzip -c "$BACKUP/db.sql.gz")
  fi
  export LEGALGIT_DATABASE_URL="postgresql+pg8000://legalgit:legalgit@localhost:$HOST_PORT/legalgit"
elif [ -f "$BACKUP/db.sqlite" ]; then
  mkdir -p "$WORK"
  cp "$BACKUP/db.sqlite" "$WORK/restore.db"
  export LEGALGIT_DATABASE_URL="sqlite:///$PWD/$WORK/restore.db"
else
  echo "no db backup found in $BACKUP" >&2
  exit 1
fi

if [ -f "$BACKUP/storage.tar.gz" ]; then
  tar xzf "$BACKUP/storage.tar.gz" -C "$WORK"
  export LEGALGIT_STORAGE_DIR="$PWD/$WORK/storage"
fi

echo "== 2. démarrage de l'API sur :$PORT"
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$PORT" &
API_PID=$!
for i in $(seq 1 20); do
  curl -sf "localhost:$PORT/healthz" >/dev/null && break
  sleep 1
done

echo "== 3. vérifications"
READY="$(curl -sf "localhost:$PORT/readyz")"
echo "  /readyz : $READY"
echo "$READY" | grep -q '"status": *"ok"'
DOCS="$(curl -sf "localhost:$PORT/v1/documents")"
echo "  documents: $(echo "$DOCS" | .venv/bin/python -c 'import sys,json; print([d["id"] for d in json.load(sys.stdin)["items"]])')"
DOC_ID="$(echo "$DOCS" | .venv/bin/python -c 'import sys,json; print(json.load(sys.stdin)["items"][0]["id"])')"
VERSIONS="$(curl -sf "localhost:$PORT/v1/documents/$DOC_ID/versions")"
echo "  snapshots restaurés: $(echo "$VERSIONS" | .venv/bin/python -c 'import sys,json; print(len(json.load(sys.stdin)["items"]))')"

echo "== restore test OK"
