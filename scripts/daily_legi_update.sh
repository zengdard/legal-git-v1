#!/usr/bin/env bash
# Daily LEGI update: download the latest daily increment, extract, import
# (idempotent — replaying a day does nothing).
#
# Usage: scripts/daily_legi_update.sh [texte_cid]
# Default texte: LEGITEXT000006070721 (Code civil).
#
# Log: var/legi/daily-update.log (rotation intégrée : 5 Mo max, 5 backups)
set -euo pipefail
cd "$(dirname "$0")/.."

TEXTE="${1:-LEGITEXT000006070721}"
BASE="https://echanges.dila.gouv.fr/OPENDATA/LEGI"
WORKDIR="var/legi"
DAILY_DIR="$WORKDIR/dailies"
EXTRACT_DIR="$WORKDIR/extracted"
LOG="$WORKDIR/daily-update.log"
ROTATE_MAX_BYTES=$((5 * 1024 * 1024))
ROTATE_KEEP=5

mkdir -p "$DAILY_DIR" "$EXTRACT_DIR"

# Rotation intégrée du journal (sans dépendance logrotate) : déclenchée
# au début de chaque exécution, la plus vieille backup est éjectée.
if [ -f "$LOG" ] && [ "$(stat -c %s "$LOG")" -gt "$ROTATE_MAX_BYTES" ]; then
  for i in $(seq $((ROTATE_KEEP - 1)) -1 1); do
    [ -f "$LOG.$i" ] && mv -f "$LOG.$i" "$LOG.$((i + 1))"
  done
  mv -f "$LOG" "$LOG.0"
fi

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG"; }

log "== démarrage mise à jour quotidienne ($TEXTE)"

# 1. find the latest daily tarball not downloaded yet
LISTING=$(curl -sf "$BASE/" | grep -oE 'LEGI_[0-9]{8}-[0-9]{6}\.tar\.gz' | sort -u)
if [ -z "$LISTING" ]; then
  log "ERREUR: listing indisponible sur $BASE"
  exit 1
fi
LATEST=$(echo "$LISTING" | tail -1)
TARGET="$DAILY_DIR/$LATEST"

if [ -f "$TARGET" ]; then
  log "aucun nouveau fichier quotidien (dernier: $LATEST)"
else
  log "téléchargement $LATEST"
  curl -sf -o "$TARGET.tmp" "$BASE/$LATEST"
  mv "$TARGET.tmp" "$TARGET"
  log "téléchargé: $(sha256sum "$TARGET" | cut -d' ' -f1)"
fi

# 2. extract (daily layout: <stamp>/legi/global/...; we extract per day)
STAMP="${LATEST#LEGI_}"; STAMP="${STAMP%.tar.gz}"
DEST="$EXTRACT_DIR/LEGI_$STAMP"
if [ ! -d "$DEST" ]; then
  mkdir -p "$DEST"
  tar xzf "$TARGET" -C "$DEST"
  log "extrait dans $DEST"
fi

# 3. import only if the daily contains our texte (most days do not change
#    the Code civil: import fails fast in that case — that is not an error)
if ! ls "$DEST"/*/*/legi/global/code_et_TNC_en_vigueur/code_en_vigueur/LEGI/TEXT/*/*/*/*/*/"$TEXTE" >/dev/null 2>&1; then
  log "rien pour $TEXTE dans $LATEST (pas de changement de ce texte ce jour-là)"
  echo "no changes for $TEXTE in $LATEST"
  exit 0
fi

# 4. import-legi uses the default DATABASE_URL/STORAGE env of the app
LEGALGIT_DATABASE_URL="${LEGALGIT_DATABASE_URL:-sqlite:///$PWD/var/legi.db}"
export LEGALGIT_DATABASE_URL
export LEGALGIT_STORAGE_DIR="${LEGALGIT_STORAGE_DIR:-$PWD/var/legi-storage}"
.venv/bin/python -m app.ingestion.cli import-legi \
  --dir "$DEST" --texte "$TEXTE" --release "$LATEST" >> "$LOG" 2>&1
log "== mise à jour terminée pour $LATEST"
echo "updated from $LATEST"
