# Enshrouded Tools

Production-focused read-only tooling for Enshrouded live stats and query inspection.

## Scope

- Steam A2S query probe for `INFO`, `PLAYER`, and `RULES`
- lane snapshot aggregation across `15636`, `15637`, and `27015`
- minimal local API/UI for `/v1/stats`, `/healthz`, and `/`
- optional webhook and Discord delivery for status-change events
- optional local CPU and memory sampling on the API host
- replay tests built from sanitized fixtures

Defaults are public-safe:
- host `127.0.0.1`
- no webhook secrets in repo
- sanitized example event payloads and fixtures

## Layout

- [`probes/query_steam_a2s.py`](/home/seslly/seslly-github/servertimeai/k8s/enshrouded_server/tools/probes/query_steam_a2s.py) - low-level A2S query tool
- [`probes/lane_probe_snapshot.py`](/home/seslly/seslly-github/servertimeai/k8s/enshrouded_server/tools/probes/lane_probe_snapshot.py) - lane-aware snapshot runner
- [`services/api/live_stats_api.py`](/home/seslly/seslly-github/servertimeai/k8s/enshrouded_server/tools/services/api/live_stats_api.py) - local API + status page
- [`fixtures/query/`](/home/seslly/seslly-github/servertimeai/k8s/enshrouded_server/tools/fixtures/query) - sanitized offline A2S fixtures
- [`tests/replay/`](/home/seslly/seslly-github/servertimeai/k8s/enshrouded_server/tools/tests/replay) - deterministic replay checks

Examples live in [`USAGE.md`](/home/seslly/seslly-github/servertimeai/k8s/enshrouded_server/tools/USAGE.md).
