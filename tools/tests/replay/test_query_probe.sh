#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROBE="${ROOT_DIR}/probes/query_steam_a2s.py"
ASSERT="${ROOT_DIR}/tests/replay/assert_query_probe.py"

OUT_JSON="$(mktemp /tmp/enshrouded-query-fixture.XXXXXX.json)"
trap 'rm -f "${OUT_JSON}"' EXIT

python3 "${PROBE}" --query-type info --decode-hex "${ROOT_DIR}/fixtures/query/a2s-info-response.hex" --summary > "${OUT_JSON}"
python3 "${ASSERT}" info "${OUT_JSON}"
python3 "${PROBE}" --query-type player --decode-hex "${ROOT_DIR}/fixtures/query/a2s-player-response.hex" --summary > "${OUT_JSON}"
python3 "${ASSERT}" player "${OUT_JSON}"
python3 "${PROBE}" --query-type rules --decode-hex "${ROOT_DIR}/fixtures/query/a2s-rules-response.hex" --summary > "${OUT_JSON}"
python3 "${ASSERT}" rules "${OUT_JSON}"
python3 "${PROBE}" --query-type all --host 127.0.0.1 --port 1 --retries 1 --timeout 0.01 > /dev/null || true

echo "test_query_probe.sh: PASS"
