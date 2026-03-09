#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNNER="${ROOT_DIR}/probes/lane_probe_snapshot.py"
FIXTURE_DIR="${ROOT_DIR}/fixtures/query"
ASSERT="${ROOT_DIR}/tests/replay/assert_lane_probe_snapshot.py"

OUT_JSON="$(mktemp /tmp/enshrouded-lane-snapshot.XXXXXX.json)"
trap 'rm -f "${OUT_JSON}"' EXIT

python3 "${RUNNER}" \
  --host 127.0.0.1 \
  --fixture-lane game_port \
  --fixture-dir "${FIXTURE_DIR}" \
  --summary > "${OUT_JSON}"
python3 "${ASSERT}" "${OUT_JSON}"

echo "test_lane_probe_snapshot.sh: PASS"
