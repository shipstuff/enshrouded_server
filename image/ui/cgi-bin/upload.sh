#!/bin/bash
set -euo pipefail

STATE_DIR="${SAVE_IMPORT_STATE_DIR:-/tmp/save-import/state}"
MARKER_FILE="${SAVE_IMPORT_MARKER_FILE:-${STATE_DIR}/result}"
WORK_DIR="/tmp/save-import/work"
UPLOAD_ZIP="${WORK_DIR}/upload.zip"
STAGE_DIR="${WORK_DIR}/stage"
MAX_UPLOAD_BYTES=104857600
MAX_UPLOAD_LIMIT_LABEL="100MB"
ENSHROUDED_BASE="${ENSHROUDED_PATH:-/home/steam/enshrouded}"
SAVEGAME_DIR="${ENSHROUDED_BASE}/savegame"
BACKUP_DIR="${SAVEGAME_DIR}/backups/$(date +%Y%m%d-%H%M%S)-preimport"

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
SLOT_IDS=("${DEFAULT_SLOT_IDS[@]}")

respond() {
  local code="$1"
  local body="$2"
  printf "Status: %s\r\n" "$code"
  printf "Content-Type: text/plain\r\n\r\n"
  printf "%s\n" "$body"
  exit 0
}

query_param() {
  local key="$1"
  local query="${QUERY_STRING:-}"
  local pair k v
  IFS='&' read -r -a pairs <<< "$query"
  for pair in "${pairs[@]}"; do
    [ -z "$pair" ] && continue
    k="${pair%%=*}"
    v="${pair#*=}"
    if [ "$k" = "$key" ]; then
      printf "%s" "$v"
      return 0
    fi
  done
  return 1
}

slot_id_from_number() {
  local slot="$1"
  if [ "$slot" -lt 1 ] || [ "$slot" -gt 10 ]; then
    return 1
  fi
  printf "%s" "${SLOT_IDS[$((slot - 1))]}"
}

slot_number_from_id() {
  local id="$1"
  local i
  for i in "${!SLOT_IDS[@]}"; do
    if [ "${SLOT_IDS[$i]}" = "$id" ]; then
      printf "%s" "$((i + 1))"
      return 0
    fi
  done
  return 1
}

is_slot_occupied() {
  local slot_id="$1"
  if [ -f "${SAVEGAME_DIR}/${slot_id}" ] || [ -f "${SAVEGAME_DIR}/${slot_id}_info" ] || [ -f "${SAVEGAME_DIR}/${slot_id}-index" ] || [ -f "${SAVEGAME_DIR}/${slot_id}_info-index" ]; then
    return 0
  fi
  return 1
}

find_first_free_slot() {
  local i slot_id
  for i in $(seq 1 10); do
    slot_id="$(slot_id_from_number "$i")"
    if ! is_slot_occupied "$slot_id"; then
      printf "%s" "$i"
      return 0
    fi
  done
  return 1
}

normalize_latest_zero() {
  local index_file="$1"
  local tmp_file="${index_file}.tmp"
  jq -e '.latest | numbers' "$index_file" >/dev/null 2>&1 || respond "400 Bad Request" "invalid index json: $(basename "$index_file")"
  jq '.latest = 0' "$index_file" > "$tmp_file" || respond "400 Bad Request" "failed to normalize index json"
  mv -f "$tmp_file" "$index_file"
}

format_epoch_utc() {
  local ts="$1"
  if [[ "$ts" =~ ^[0-9]+$ ]]; then
    date -u -d "@$ts" '+%Y-%m-%d %H:%M:%S UTC' 2>/dev/null || printf "%s" "$ts"
  else
    printf "unknown"
  fi
}

SOURCE_ID=""
SOURCE_INDEX_FILE=""
SOURCE_INFO_INDEX_FILE=""
SOURCE_BASE_FILE=""
SOURCE_INFO_FILE=""

detect_source_files() {
  local entries="$1"
  local entry base id
  local source_id_from_index=""
  local source_id_from_info_index=""
  local source_id_from_base_file=""
  local source_id_from_info_file=""

  while IFS= read -r entry; do
    [ -z "$entry" ] && continue
    base="$(basename "$entry")"
    if [ "$base" != "$entry" ]; then
      respond "400 Bad Request" "zip entries must be top-level files only"
    fi

    if [[ "$base" == *_info-index ]]; then
      id="${base%_info-index}"
      [ -n "$source_id_from_info_index" ] && [ "$source_id_from_info_index" != "$id" ] && respond "400 Bad Request" "multiple slot ids in _info-index files"
      source_id_from_info_index="$id"
      SOURCE_INFO_INDEX_FILE="$base"
      continue
    fi

    if [[ "$base" == *-index ]]; then
      id="${base%-index}"
      [ -n "$source_id_from_index" ] && [ "$source_id_from_index" != "$id" ] && respond "400 Bad Request" "multiple slot ids in -index files"
      source_id_from_index="$id"
      SOURCE_INDEX_FILE="$base"
      continue
    fi

    if [[ "$base" == *_info-[0-9]* ]]; then
      id="${base%%_info-*}"
      [ -n "$source_id_from_info_file" ] && [ "$source_id_from_info_file" != "$id" ] && respond "400 Bad Request" "multiple slot ids in _info files"
      source_id_from_info_file="$id"
      SOURCE_INFO_FILE="$base"
      continue
    fi

    if [[ "$base" == *_info ]]; then
      id="${base%_info}"
      [ -n "$source_id_from_info_file" ] && [ "$source_id_from_info_file" != "$id" ] && respond "400 Bad Request" "multiple slot ids in _info files"
      source_id_from_info_file="$id"
      SOURCE_INFO_FILE="$base"
      continue
    fi

    if [[ "$base" == *-[0-9]* ]]; then
      id="${base%-*}"
      [ -n "$source_id_from_base_file" ] && [ "$source_id_from_base_file" != "$id" ] && respond "400 Bad Request" "multiple slot ids in save payload files"
      source_id_from_base_file="$id"
      SOURCE_BASE_FILE="$base"
      continue
    fi

    if [[ "$base" == *-* ]]; then
      respond "400 Bad Request" "unexpected filename: $base"
    fi

    [ -n "$source_id_from_base_file" ] && [ "$source_id_from_base_file" != "$base" ] && respond "400 Bad Request" "multiple slot ids in save payload files"
    source_id_from_base_file="$base"
    SOURCE_BASE_FILE="$base"
  done <<EOF
$entries
EOF

  [ -z "$source_id_from_index" ] && respond "400 Bad Request" "missing <id>-index"
  [ -z "$source_id_from_info_index" ] && respond "400 Bad Request" "missing <id>_info-index"
  [ "$source_id_from_index" != "$source_id_from_info_index" ] && respond "400 Bad Request" "index files have different slot ids"

  SOURCE_ID="$source_id_from_index"
  [ -z "$SOURCE_BASE_FILE" ] && respond "400 Bad Request" "missing save payload file"
  [ -z "$SOURCE_INFO_FILE" ] && respond "400 Bad Request" "missing save info file"

  if [ "$SOURCE_BASE_FILE" != "$SOURCE_ID" ]; then
    if [[ "$SOURCE_BASE_FILE" != "${SOURCE_ID}-"* ]]; then
      respond "400 Bad Request" "invalid save payload filename: ${SOURCE_BASE_FILE}"
    fi
    payload_suffix="${SOURCE_BASE_FILE#${SOURCE_ID}-}"
    [[ ! "$payload_suffix" =~ ^[0-9]+$ ]] && respond "400 Bad Request" "invalid save payload filename: ${SOURCE_BASE_FILE}"
  fi

  if [ "$SOURCE_INFO_FILE" != "${SOURCE_ID}_info" ]; then
    if [[ "$SOURCE_INFO_FILE" != "${SOURCE_ID}_info-"* ]]; then
      respond "400 Bad Request" "invalid save info filename: ${SOURCE_INFO_FILE}"
    fi
    info_suffix="${SOURCE_INFO_FILE#${SOURCE_ID}_info-}"
    [[ ! "$info_suffix" =~ ^[0-9]+$ ]] && respond "400 Bad Request" "invalid save info filename: ${SOURCE_INFO_FILE}"
  fi

  [ -n "$source_id_from_base_file" ] && [ "$source_id_from_base_file" != "$SOURCE_ID" ] && respond "400 Bad Request" "save payload slot id does not match index slot id"
  [ -n "$source_id_from_info_file" ] && [ "$source_id_from_info_file" != "$SOURCE_ID" ] && respond "400 Bad Request" "save info slot id does not match index slot id"
}

if [ "${REQUEST_METHOD:-}" != "POST" ]; then
  respond "405 Method Not Allowed" "method not allowed (use POST)"
fi

if [ "${CONTENT_LENGTH:-0}" -le 0 ]; then
  respond "400 Bad Request" "missing request body"
fi

if [ "${CONTENT_LENGTH}" -gt "${MAX_UPLOAD_BYTES}" ]; then
  respond "413 Payload Too Large" "upload exceeds ${MAX_UPLOAD_LIMIT_LABEL} limit; this importer only accepts normal Enshrouded world-save zips to reduce accidental or unsafe uploads"
fi

mkdir -p "$STATE_DIR" "$WORK_DIR" "$STAGE_DIR" "$SAVEGAME_DIR"
rm -f "$UPLOAD_ZIP"
rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR"

cat > "$UPLOAD_ZIP"

ZIP_ENTRIES="$(unzip -Z1 "$UPLOAD_ZIP" 2>/dev/null || true)"
[ -z "$ZIP_ENTRIES" ] && respond "400 Bad Request" "invalid zip or empty archive"

ENTRY_COUNT="$(printf "%s\n" "$ZIP_ENTRIES" | sed '/^$/d' | wc -l | tr -d ' ')"
[ "$ENTRY_COUNT" -ne 4 ] && respond "400 Bad Request" "zip must contain exactly 4 files"

detect_source_files "$ZIP_ENTRIES"

SOURCE_SLOT="$(slot_number_from_id "$SOURCE_ID" || true)"
[ -z "$SOURCE_SLOT" ] && respond "400 Bad Request" "uploaded slot id ${SOURCE_ID} is not in supported slot list"

TARGET_SLOT_REQUESTED="$(query_param target_slot || true)"
TARGET_MODE="$(query_param target_mode || true)"
TARGET_MODE="${TARGET_MODE:-auto}"
CONFIRM_OVERWRITE="$(query_param confirm_overwrite || true)"
CONFIRM_OVERWRITE="${CONFIRM_OVERWRITE:-0}"

if [ "$TARGET_MODE" = "specific" ] || [ -n "$TARGET_SLOT_REQUESTED" ]; then
  if ! [[ "$TARGET_SLOT_REQUESTED" =~ ^[0-9]+$ ]] || [ "$TARGET_SLOT_REQUESTED" -lt 1 ] || [ "$TARGET_SLOT_REQUESTED" -gt 10 ]; then
    respond "400 Bad Request" "target_slot must be 1-10"
  fi
  DEST_SLOT="$TARGET_SLOT_REQUESTED"
elif [ "$TARGET_MODE" = "source" ]; then
  DEST_SLOT="$SOURCE_SLOT"
else
  DEST_SLOT="$(find_first_free_slot || true)"
  [ -z "$DEST_SLOT" ] && DEST_SLOT="$SOURCE_SLOT"
fi

DEST_ID="$(slot_id_from_number "$DEST_SLOT")"
DEST_OCCUPIED=0
if is_slot_occupied "$DEST_ID"; then
  DEST_OCCUPIED=1
fi

SOURCE_TIME_RAW="$(unzip -p "$UPLOAD_ZIP" "$SOURCE_INDEX_FILE" 2>/dev/null | jq -r '.time // empty' 2>/dev/null || true)"
DEST_TIME_RAW="$(jq -r '.time // empty' "${SAVEGAME_DIR}/${DEST_ID}-index" 2>/dev/null || true)"
SOURCE_TIME_FMT="$(format_epoch_utc "$SOURCE_TIME_RAW")"
DEST_TIME_FMT="$(format_epoch_utc "$DEST_TIME_RAW")"

WARNINGS=()
if [ "$SOURCE_SLOT" -ne "$DEST_SLOT" ]; then
  WARNINGS+=("Uploaded world appears to be Save ${SOURCE_SLOT} (updated ${SOURCE_TIME_FMT}); it will be imported into Save ${DEST_SLOT}.")
fi
if [ "$DEST_OCCUPIED" -eq 1 ]; then
  WARNINGS+=("Save ${DEST_SLOT} already exists (updated ${DEST_TIME_FMT}) and will be overwritten.")
fi

if [ "${#WARNINGS[@]}" -gt 0 ] && [ "$CONFIRM_OVERWRITE" != "1" ]; then
  warn_text=""
  for w in "${WARNINGS[@]}"; do
    if [ -n "$warn_text" ]; then
      warn_text="${warn_text} "
    fi
    warn_text="${warn_text}${w}"
  done
  respond "409 Conflict" "${warn_text} Re-submit with confirm_overwrite=1 to proceed."
fi

unzip -j -o "$UPLOAD_ZIP" -d "$STAGE_DIR" >/dev/null 2>&1 || respond "400 Bad Request" "failed to extract zip"

SOURCE_FILES=("$SOURCE_BASE_FILE" "$SOURCE_INFO_FILE" "$SOURCE_INDEX_FILE" "$SOURCE_INFO_INDEX_FILE")
for f in "${SOURCE_FILES[@]}"; do
  [ ! -s "${STAGE_DIR}/${f}" ] && respond "400 Bad Request" "required file missing or empty: ${f}"
done

# Strip payload backup suffixes so imported world becomes the active file.
[ "$SOURCE_BASE_FILE" != "$SOURCE_ID" ] && mv -f "${STAGE_DIR}/${SOURCE_BASE_FILE}" "${STAGE_DIR}/${SOURCE_ID}"
[ "$SOURCE_INFO_FILE" != "${SOURCE_ID}_info" ] && mv -f "${STAGE_DIR}/${SOURCE_INFO_FILE}" "${STAGE_DIR}/${SOURCE_ID}_info"

# Remap source slot IDs to destination slot IDs.
mv -f "${STAGE_DIR}/${SOURCE_ID}" "${STAGE_DIR}/${DEST_ID}"
mv -f "${STAGE_DIR}/${SOURCE_ID}_info" "${STAGE_DIR}/${DEST_ID}_info"
mv -f "${STAGE_DIR}/${SOURCE_INDEX_FILE}" "${STAGE_DIR}/${DEST_ID}-index"
mv -f "${STAGE_DIR}/${SOURCE_INFO_INDEX_FILE}" "${STAGE_DIR}/${DEST_ID}_info-index"

normalize_latest_zero "${STAGE_DIR}/${DEST_ID}-index"
normalize_latest_zero "${STAGE_DIR}/${DEST_ID}_info-index"

TARGET_FILES=("${DEST_ID}" "${DEST_ID}_info" "${DEST_ID}-index" "${DEST_ID}_info-index")
mkdir -p "$BACKUP_DIR"
for f in "${TARGET_FILES[@]}"; do
  [ -f "${SAVEGAME_DIR}/${f}" ] && cp "${SAVEGAME_DIR}/${f}" "${BACKUP_DIR}/${f}"
done

for f in "${TARGET_FILES[@]}"; do
  cp "${STAGE_DIR}/${f}" "${SAVEGAME_DIR}/.${f}.new"
done
for f in "${TARGET_FILES[@]}"; do
  mv -f "${SAVEGAME_DIR}/.${f}.new" "${SAVEGAME_DIR}/${f}"
done

printf "uploaded" > "$MARKER_FILE"
respond "200 OK" "world uploaded from Save ${SOURCE_SLOT} into Save ${DEST_SLOT}; latest=0 applied"
