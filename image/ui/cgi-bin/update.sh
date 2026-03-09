#!/bin/sh
set -eu

STATE_DIR="${SAVE_IMPORT_STATE_DIR:-/tmp/save-import/state}"
MARKER_FILE="${SAVE_IMPORT_MARKER_FILE:-${STATE_DIR}/result}"
mkdir -p "$STATE_DIR"

printf "Content-Type: text/plain\r\n\r\n"

if [ "${REQUEST_METHOD:-}" != "POST" ]; then
  printf "method not allowed (use POST)\n"
  exit 0
fi

printf "update" > "$MARKER_FILE"
printf "Requested Steam update check, then server startup.\n"
