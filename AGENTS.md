# Enshrouded Server Repo Guide

Keep `AGENTS.md` and `CLAUDE.md` in sync. This repo ships an Enshrouded dedicated server bundle across multiple deployment targets plus a small stats API and replayable probes/tests.

## What Lives Where

- `README.md`: public operator-facing docs. Update this when behavior or install flows change.
- `image/`: main game-server container image.
- `image/entrypoint.sh`: real startup logic for SteamCMD, Proton, config generation, optional save-import UI, update-on-boot, and graceful shutdown.
- `image/ui/`: static files and CGI helpers for the temporary save import UI.
- `tools/probes/`: offline and live UDP probe tools for the game/query lanes.
- `tools/services/api/live_stats_api.py`: lightweight HTTP API and landing page server for `/`, `/healthz`, and `/v1/stats`, plus webhook and Discord delivery.
- `tools/services/api/static/index.html`: API landing page.
- `tools/tests/replay/`: replay tests for probes and API behavior. These are the fastest safety net and should stay passing.
- `docker-compose.yaml`: local container deployment using the main image plus optional stats API sidecar.
- `namespace.yaml`, `pvc.yaml`, `statefulset.yaml`, `service.yaml`: plain Kubernetes manifests.
- `helm/enshrouded/`: Helm chart. Keep chart values, templates, and README examples aligned.
- `bare-linux/`: non-container install path using `systemd` and the same `image/entrypoint.sh`.
- `.github/workflows/`: CI, image publish, and chart publish workflows.

## Deployment Surfaces

There are four first-class install paths:

1. Docker Compose via `docker-compose.yaml`
2. Plain Kubernetes via the root manifests
3. Helm via `helm/enshrouded`
4. Bare Linux via `bare-linux/install.sh`

When changing ports, env vars, image names, or runtime modes, check all four surfaces. This repo is easy to drift because each surface exposes similar knobs in a different form.

## Startup And Config Model

`image/entrypoint.sh` is the source of truth for runtime behavior.

Supported config modes:

- `env`: default outside Helm; copies the example config if needed and patches selected values from env on each start
- `managed`: renders a full JSON template and merges password values from a secret-backed JSON map
- `mutable`: requires an existing config file and leaves it untouched

Important details:

- Save-import UI is disabled unless `SAVE_IMPORT_MODE=1`.
- `SAVE_IMPORT_BIND` defaults to `127.0.0.1` on purpose.
- Managed mode ignores inline `userGroups[].password` values and expects passwords from a JSON secret map.
- Bare Linux uses the same entrypoint as the container paths, so startup changes often affect both container and bare-metal installs.

## Stats API Model

The stats API is intentionally simple:

- serves `/`, `/healthz`, `/v1/stats`
- uses `tools/probes/lane_probe_snapshot.py` for the live snapshot
- optionally samples local CPU and memory from the machine running the API
- can post webhook events to a generic JSON endpoint and directly to Discord

Current behavior to understand before editing:

- `ENSHROUDED_API_HOST` is the UDP probe target.
- In Kubernetes the sidecar currently probes `127.0.0.1`, so that same value appears in API payloads and webhook messages.
- The landing page under `tools/services/api/static/index.html` is a read-only status view; it depends on the JSON shape from `/v1/stats`.

If you change API payload fields, update:

- `tools/services/api/live_stats_api.py`
- `tools/services/api/static/index.html`
- `tools/tests/replay/test_live_stats_api.py`
- `tools/USAGE.md`
- `README.md`

## Kubernetes And Helm Notes

- Root `statefulset.yaml` is the plain-manifest install path.
- `helm/enshrouded/templates/statefulset.yaml.tpl` is the Helm version of the same workload and must stay semantically aligned.
- Helm defaults to `serverConfig.mode=managed`.
- Plain manifests currently behave more like the image default path and rely on env mode.
- If you add or rename env vars, check both the plain StatefulSet and the Helm template.
- If you change chart values, update `helm/enshrouded/values.yaml`, template references, and the README install examples.

## Tests And Validation

Fast local checks:

```bash
bash ./tools/tests/replay/test_query_probe.sh
bash ./tools/tests/replay/test_lane_probe_snapshot.sh
bash ./tools/tests/replay/test_live_stats_api.sh
python3 ./tools/tests/replay/test_query_steam_a2s.py ./tools
helm template enshrouded ./helm/enshrouded >/dev/null
```

CI already runs the replay tests and a Helm render. If you touch probes, API payloads, or chart templates, run the relevant checks before finishing.

## Editing Rules For This Repo

- Prefer small, synchronized changes across docs and deployment surfaces over fixing only one path.
- Never commit real secrets. Passwords and webhook URLs should come from env vars or Kubernetes Secrets.
- If you touch runtime defaults, update the operator docs in `README.md`.
- If you touch install behavior for bare Linux, also check `bare-linux/README.md` and the example service files.
- If you touch the save-import UI flow, inspect both `image/ui/` and the entrypoint logic.
- If you touch published artifact names or tags, check both image and chart workflows in `.github/workflows/`.
