#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

python3 "${ROOT_DIR}/tests/replay/test_live_stats_api.py" "${ROOT_DIR}"

echo "test_live_stats_api.sh: PASS"
