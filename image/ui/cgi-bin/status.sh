#!/bin/bash
set -euo pipefail

ENSHROUDED_BASE="${ENSHROUDED_PATH:-/home/steam/enshrouded}"
SAVEGAME_DIR="${ENSHROUDED_BASE}/savegame"

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

printf "Content-Type: application/json\r\n\r\n"

mkdir -p "$SAVEGAME_DIR"

items=()
occupied_count=0

for idx in "${!DEFAULT_SLOT_IDS[@]}"; do
  slot=$((idx + 1))
  slot_id="${DEFAULT_SLOT_IDS[$idx]}"
  index_file="${SAVEGAME_DIR}/${slot_id}-index"
  info_index_file="${SAVEGAME_DIR}/${slot_id}_info-index"
  count=0
  [ -f "${SAVEGAME_DIR}/${slot_id}" ] && count=$((count + 1))
  [ -f "${SAVEGAME_DIR}/${slot_id}_info" ] && count=$((count + 1))
  [ -f "$index_file" ] && count=$((count + 1))
  [ -f "$info_index_file" ] && count=$((count + 1))
  if [ "$count" -gt 0 ]; then
    occupied=true
    occupied_count=$((occupied_count + 1))
  else
    occupied=false
  fi

  latest="null"
  updated="null"
  info_latest="null"
  info_updated="null"

  if [ -f "$index_file" ]; then
    val="$(jq -r '.latest // empty' "$index_file" 2>/dev/null || true)"
    [ -n "$val" ] && latest="$val"
    val="$(jq -r '.time // empty' "$index_file" 2>/dev/null || true)"
    [ -n "$val" ] && updated="$val"
  fi

  if [ -f "$info_index_file" ]; then
    val="$(jq -r '.latest // empty' "$info_index_file" 2>/dev/null || true)"
    [ -n "$val" ] && info_latest="$val"
    val="$(jq -r '.time // empty' "$info_index_file" 2>/dev/null || true)"
    [ -n "$val" ] && info_updated="$val"
  fi

  items+=("{\"slot\":${slot},\"slotId\":\"${slot_id}\",\"occupied\":${occupied},\"fileCount\":${count},\"latest\":${latest},\"updatedAt\":${updated},\"infoLatest\":${info_latest},\"infoUpdatedAt\":${info_updated}}")
done

slots_json="["
for i in "${!items[@]}"; do
  [ "$i" -gt 0 ] && slots_json+=","
  slots_json+="${items[$i]}"
done
slots_json+="]"

printf "{\"slotCount\":%s,\"occupiedCount\":%s,\"slots\":%s}\n" "${#DEFAULT_SLOT_IDS[@]}" "$occupied_count" "$slots_json"
