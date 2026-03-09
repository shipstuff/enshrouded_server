# How To Install An Enshrouded Self-Hosted Server

Open-source deployment bundle for running an Enshrouded self-hosted server or Enshrouded dedicated server on a spare PC, with Docker, or on Kubernetes.

This repo is aimed at operators who want a self-hosted Enshrouded server with multiple deployment options: bare Linux, Docker Compose, plain Kubernetes manifests, and a Helm chart.

This repo includes:
- a game-server image in [`image/`](/home/seslly/seslly-github/servertimeai/k8s/enshrouded_server/image)
- an optional lightweight stats API in [`tools/services/api/`](/home/seslly/seslly-github/servertimeai/k8s/enshrouded_server/tools/services/api)
- Docker Compose, plain Kubernetes manifests, and a Helm chart
- a bare-Linux installer for running the server as a user systemd service
- replayable probe/API tests in [`tools/tests/replay/`](/home/seslly/seslly-github/servertimeai/k8s/enshrouded_server/tools/tests/replay)

Use this repo if you want to:
- deploy an Enshrouded self-hosted server with Docker Compose
- run an Enshrouded dedicated server on Kubernetes with Helm or plain manifests
- host an Enshrouded server on a spare Linux machine without containers
- expose simple live metrics and Discord webhook notifications for an Enshrouded server

## Choose An Install Path

If you are here to install an Enshrouded server, start with one of these:

- [Install With Docker Compose](#install-with-docker-compose)
- [Install On Kubernetes With Plain Manifests Or Kustomize](#install-on-kubernetes-with-plain-manifests-or-kustomize)
- [Install On Kubernetes With Helm](#install-on-kubernetes-with-helm)
- [Install On Bare Linux With systemd](#install-on-bare-linux-with-systemd)

## Published Images And Helm Chart

- `ghcr.io/shipstuff/enshrouded-server`
- `ghcr.io/shipstuff/enshrouded-live-stats-api`

Published public Helm chart:
- `oci://ghcr.io/shipstuff/charts/enshrouded`

The Helm chart is validated on pull requests and `main`, and published to GHCR as an OCI chart on version tags like `v0.1.0`. The git tag must match [`Chart.yaml`](/home/seslly/seslly-github/servertimeai/k8s/enshrouded_server/helm/enshrouded/Chart.yaml#L1) `version`.

## Install With Docker Compose

Use the published images:

```bash
docker compose up -d
```

Build locally instead:

```bash
docker compose up -d --build
```

Override runtime defaults through shell env or a local `.env` file:

```bash
SERVER_NAME="My Enshrouded Server" \
SAVE_IMPORT_MODE=1 \
SAVE_IMPORT_BIND=127.0.0.1 \
docker compose up -d
```

Published-image overrides:

```bash
ENSHROUDED_IMAGE=ghcr.io/your-org/enshrouded-server:latest \
ENSHROUDED_STATS_API_IMAGE=ghcr.io/your-org/enshrouded-live-stats-api:latest \
docker compose up -d
```

Default exposed ports:
- UDP `15636`
- UDP `15637`
- UDP `27015`
- TCP `8091` for the stats API
- TCP `8080` only matters when `SAVE_IMPORT_MODE=1`

## Install On Kubernetes With Plain Manifests Or Kustomize

Apply the included manifests:

```bash
kubectl apply -f namespace.yaml
kubectl apply -f pvc.yaml
kubectl apply -f statefulset.yaml
kubectl apply -f service.yaml
```

Or use the repo-root Kustomize wrapper:

```bash
kubectl apply -k .
```

The plain manifest defaults point at GHCR. If you publish under your own registry, update the image fields in [`statefulset.yaml`](/home/seslly/seslly-github/servertimeai/k8s/enshrouded_server/statefulset.yaml) or patch them after apply:

```bash
kubectl -n games set image statefulset/enshrouded \
  enshrouded=ghcr.io/your-org/enshrouded-server:latest \
  enshrouded-stats-api=ghcr.io/your-org/enshrouded-live-stats-api:latest
```

## Install On Kubernetes With Helm

Install with the public defaults:

```bash
helm upgrade --install enshrouded ./helm/enshrouded \
  --namespace games --create-namespace
```

Install the published OCI chart instead:

```bash
helm upgrade --install enshrouded oci://ghcr.io/shipstuff/charts/enshrouded \
  --version 0.1.0 \
  --namespace games --create-namespace
```

Typical overrides:

```bash
helm upgrade --install enshrouded ./helm/enshrouded \
  --namespace games --create-namespace \
  --set image.repository=ghcr.io/your-org/enshrouded-server \
  --set statsApi.image.repository=ghcr.io/your-org/enshrouded-live-stats-api \
  --set image.tag=v1.0.0 \
  --set statsApi.image.tag=v1.0.0
```

The chart also supports:
- `imagePullSecrets`
- disabling the sidecar API with `--set statsApi.enabled=false`
- enabling the save-import UI service with `--set service.saveImport.enabled=true`

Helm now supports two server-config ownership modes:
- `serverConfig.mode=managed`: render `serverConfig.inlineJson` on every start and merge `userGroups` passwords from a Secret
- `serverConfig.mode=mutable`: require an existing JSON file on the PVC and leave it untouched

Managed mode is the default. The inline config is checked into values, while passwords come from a Secret JSON map keyed by group name. Inline `userGroups[].password` values are ignored at startup on purpose.

Example password secret:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: enshrouded-server-passwords
  namespace: games
stringData:
  user-group-passwords.json: |
    {"Default":"replace-me"}
```

Use it with Helm:

```bash
helm upgrade --install enshrouded ./helm/enshrouded \
  --namespace games --create-namespace \
  --set serverConfig.passwordSecret.name=enshrouded-server-passwords
```

If you want the UI or manual edits to own the config file instead, switch to mutable mode:

```bash
helm upgrade --install enshrouded ./helm/enshrouded \
  --namespace games --create-namespace \
  --set serverConfig.mode=mutable
```

To expose the startup save-import UI on a node port:

```bash
helm upgrade --install enshrouded ./helm/enshrouded \
  --namespace games --create-namespace \
  --set service.saveImport.enabled=true \
  --set service.saveImport.nodePort=32080 \
  --set saveImport.bind=0.0.0.0
```

## Install On Bare Linux With systemd

Install as your current user with rootless `systemd --user`:

```bash
./bare-linux/install.sh
```

Details and installer-only env vars are documented in [`bare-linux/README.md`](/home/seslly/seslly-github/servertimeai/k8s/enshrouded_server/bare-linux/README.md).

## Configure Server Runtime

The server config lives at `$ENSHROUDED_PATH/enshrouded_server.json`.
In `env` mode, if the file does not exist, the image copies [`image/enshrouded_server_example.json`](/home/seslly/seslly-github/servertimeai/k8s/enshrouded_server/image/enshrouded_server_example.json) and applies env overrides on each start.

Runtime config modes:
- `env` (default outside Helm): copy the example config if needed and apply selected env overrides on every start
- `managed`: render a full config template and merge password values from a secret-backed JSON map
- `mutable`: require an existing config file and do not rewrite it

Common env overrides:

| Env var | Default | Purpose |
|---|---|---|
| `SERVER_NAME` | `Enshrouded Server` | Server browser name |
| `PORT` | `15637` | Query/game config port |
| `SERVER_SLOTS` | `16` | Max players |
| `ENABLE_TEXT_CHAT` | `false` | Enable text chat |
| `SAVE_IMPORT_MODE` | `0` | Startup save-import UI gate |
| `SAVE_IMPORT_BIND` | `127.0.0.1` | Save-import bind address |
| `SAVE_IMPORT_PORT` | `8080` | Save-import HTTP port |
| `EXTERNAL_CONFIG` | `0` | Use your own JSON config without env patching |
| `ENSHROUDED_CONFIG_MODE` | auto | `env`, `managed`, or `mutable` |
| `AUTO_UPDATE_ON_BOOT` | `0` | Run Steam update/validate during startup |

When `EXTERNAL_CONFIG=1` or `ENSHROUDED_CONFIG_MODE=mutable`, you must provide your own `enshrouded_server.json` at `ENSHROUDED_CONFIG`.
When `ENSHROUDED_CONFIG_MODE=managed`, set `ENSHROUDED_MANAGED_CONFIG_TEMPLATE` to a full JSON template and optionally `ENSHROUDED_MANAGED_CONFIG_PASSWORDS` to a secret-backed JSON map like `{"Default":"replace-me"}`.

## Use The Optional Stats API And Landing Page

The optional API exposes:
- `/healthz`
- `/v1/stats`
- `/`

Default port: `8091`.

The API sidecar is enabled by default in Helm and the plain StatefulSet.
For local usage outside Kubernetes:

```bash
python3 ./tools/services/api/live_stats_api.py \
  --host 127.0.0.1 \
  --game-port-1 15636 \
  --game-port-2 15637 \
  --steam-query-port 27015 \
  --bind 127.0.0.1 \
  --port 8091
```

More examples live in [`tools/USAGE.md`](/home/seslly/seslly-github/servertimeai/k8s/enshrouded_server/tools/USAGE.md).

## Use The Optional Save Import UI

The temporary upload/download UI is disabled by default.
Enable it for a single boot by setting `SAVE_IMPORT_MODE=1`.

Safer default:
- `SAVE_IMPORT_BIND=127.0.0.1`

Only switch `SAVE_IMPORT_BIND` to `0.0.0.0` if you intentionally want to expose the UI over the network.

## Validate Local Changes

Replay checks:

```bash
bash ./tools/tests/replay/test_query_probe.sh
bash ./tools/tests/replay/test_lane_probe_snapshot.sh
bash ./tools/tests/replay/test_live_stats_api.sh
python3 ./tools/tests/replay/test_query_steam_a2s.py ./tools
```

Optional Helm render check:

```bash
helm template enshrouded ./helm/enshrouded >/dev/null
```

Optional Kustomize render check:

```bash
kubectl kustomize . >/dev/null
```
