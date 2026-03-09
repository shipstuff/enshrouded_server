#!/bin/bash
set -euo pipefail

ENSHROUDED_BASE="${ENSHROUDED_PATH:-/home/steam/enshrouded}"
SAVEGAME_DIR="${ENSHROUDED_BASE}/savegame"
WORK_DIR="/tmp/save-import/work"
EXPORT_DIR="${WORK_DIR}/export"
STAMP="$(date +%Y%m%d-%H%M%S)"
ZIP_NAME="enshrouded-saves-${STAMP}.zip"
ZIP_PATH="${WORK_DIR}/${ZIP_NAME}"

DEFAULT_SLOT_IDS=(
  "3ad85aea"
  "3bd85c7d"
  "38d857c4"
  "39d85957"
  "36d8549e"
  "37d85631"
  "34d85178"
  "35d8530b"
  "32d84e52"
  "33d84fe5"
)

respond_text() {
  local code="$1"
  local body="$2"
  printf "Status: %s\r\n" "$code"
  printf "Content-Type: text/plain\r\n\r\n"
  printf "%s\n" "$body"
  exit 0
}

if [ "${REQUEST_METHOD:-}" != "GET" ]; then
  respond_text "405 Method Not Allowed" "method not allowed (use GET)"
fi

mkdir -p "$WORK_DIR"
rm -rf "$EXPORT_DIR"
mkdir -p "$EXPORT_DIR"
rm -f "$ZIP_PATH"

copied=0
for slot_id in "${DEFAULT_SLOT_IDS[@]}"; do
  for file in \
    "${SAVEGAME_DIR}/${slot_id}" \
    "${SAVEGAME_DIR}/${slot_id}_info" \
    "${SAVEGAME_DIR}/${slot_id}-index" \
    "${SAVEGAME_DIR}/${slot_id}_info-index" \
    "${SAVEGAME_DIR}/${slot_id}-"[0-9]* \
    "${SAVEGAME_DIR}/${slot_id}_info-"[0-9]*; do
    [ -f "$file" ] || continue
    cp "$file" "${EXPORT_DIR}/$(basename "$file")"
    copied=$((copied + 1))
  done
done

if [ "$copied" -eq 0 ]; then
  respond_text "404 Not Found" "no save files found to export"
fi

python3 - "$EXPORT_DIR" "$ZIP_PATH" <<'PY'
import os
import sys
import zipfile

src_dir = sys.argv[1]
zip_path = sys.argv[2]

with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for name in sorted(os.listdir(src_dir)):
        full_path = os.path.join(src_dir, name)
        if os.path.isfile(full_path):
            zf.write(full_path, arcname=name)
PY

[ -f "$ZIP_PATH" ] || respond_text "500 Internal Server Error" "failed to build export archive"

printf "Status: 200 OK\r\n"
printf "Content-Type: application/zip\r\n"
printf "Content-Disposition: attachment; filename=\"%s\"\r\n" "$ZIP_NAME"
printf "Cache-Control: no-store\r\n\r\n"
cat "$ZIP_PATH"
