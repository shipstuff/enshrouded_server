# Usage

## 1) Decode A Fixture Offline

```bash
python3 ./tools/probes/query_steam_a2s.py \
  --query-type info \
  --decode-hex ./tools/fixtures/query/a2s-info-response.hex \
  --summary
```

```bash
python3 ./tools/probes/query_steam_a2s.py \
  --query-type player \
  --decode-hex ./tools/fixtures/query/a2s-player-response.hex \
  --summary
```

```bash
python3 ./tools/probes/query_steam_a2s.py \
  --query-type rules \
  --decode-hex ./tools/fixtures/query/a2s-rules-response.hex \
  --summary
```

## 2) Probe One Lane

Local/default ports:

```bash
python3 ./tools/probes/query_steam_a2s.py \
  --query-type all \
  --host 127.0.0.1 \
  --port 15637 \
  --timeout 1.5 \
  --retries 2 \
  --summary
```

If you are probing a Kubernetes NodePort instead, pass the node address and NodePort explicitly.

## 3) Snapshot All Lanes

```bash
python3 ./tools/probes/lane_probe_snapshot.py \
  --host 127.0.0.1 \
  --game-port-1 15636 \
  --game-port-2 15637 \
  --steam-query-port 27015 \
  --summary
```

Offline replay:

```bash
python3 ./tools/probes/lane_probe_snapshot.py \
  --host 127.0.0.1 \
  --fixture-lane game_port_2 \
  --fixture-dir ./tools/fixtures/query \
  --summary
```

## 4) Run The Local API/UI

```bash
python3 ./tools/services/api/live_stats_api.py \
  --host 127.0.0.1 \
  --game-port-1 15636 \
  --game-port-2 15637 \
  --steam-query-port 27015 \
  --bind 127.0.0.1 \
  --port 8091
```

Then open `http://127.0.0.1:8091/`.

## 5) Expose Local CPU And Memory Stats

```bash
python3 ./tools/services/api/live_stats_api.py \
  --host 127.0.0.1 \
  --game-port-1 15636 \
  --game-port-2 15637 \
  --steam-query-port 27015 \
  --bind 127.0.0.1 \
  --port 8091 \
  --expose-local-stats
```

Equivalent env:

```bash
export ENSHROUDED_API_EXPOSE_LOCAL_STATS=1
```

## 6) Configure Webhook Events

```bash
python3 ./tools/services/api/live_stats_api.py \
  --host 127.0.0.1 \
  --game-port-1 15636 \
  --game-port-2 15637 \
  --steam-query-port 27015 \
  --webhook-url https://example.invalid/hooks/enshrouded \
  --webhook-events up,down,player_add,player_remove,high_latency,high_memory,high_cpu \
  --webhook-high-latency-ms 200 \
  --webhook-high-memory-percent 85 \
  --webhook-high-cpu-percent 90
```

Equivalent env:

```bash
export ENSHROUDED_API_WEBHOOK_URL=https://example.invalid/hooks/enshrouded
export ENSHROUDED_API_WEBHOOK_EVENTS=up,down,player_add,player_remove,high_latency,high_memory,high_cpu
export ENSHROUDED_API_WEBHOOK_HIGH_LATENCY_MS=200
export ENSHROUDED_API_WEBHOOK_HIGH_MEMORY_PERCENT=85
export ENSHROUDED_API_WEBHOOK_HIGH_CPU_PERCENT=90
```

## 7) Send Events Directly To Discord

```bash
python3 ./tools/services/api/live_stats_api.py \
  --host 127.0.0.1 \
  --discord-webhook-url https://discord.com/api/webhooks/... \
  --webhook-events up,down,player_add,player_remove,high_latency,high_memory,high_cpu \
  --webhook-high-latency-ms 200 \
  --webhook-high-memory-percent 85 \
  --webhook-high-cpu-percent 90
```

Equivalent env:

```bash
export ENSHROUDED_API_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

## 8) Log Events Without A Webhook

```bash
python3 ./tools/services/api/live_stats_api.py \
  --host 127.0.0.1 \
  --game-port-1 15636 \
  --game-port-2 15637 \
  --steam-query-port 27015 \
  --log-events \
  --webhook-events up,down,player_add,player_remove,high_latency,high_memory,high_cpu \
  --webhook-high-latency-ms 200 \
  --webhook-high-memory-percent 85 \
  --webhook-high-cpu-percent 90
```

Equivalent env:

```bash
export ENSHROUDED_API_LOG_EVENTS=1
```

Example event payload:

```json
{
  "event": "player_add",
  "ts": "2026-03-06T20:00:06Z",
  "host": "127.0.0.1",
  "details": {
    "delta": 1,
    "players_previous": 2,
    "players_current": 3
  },
  "live": {
    "status": "online",
    "source": "query",
    "source_lane": "game_port_2",
    "players_current": 3,
    "players_max": 16,
    "players_confidence": "high",
    "server_name": "Enshrouded Server",
    "server_version": "0.8.1.0",
    "latency_ms": 148.2
  },
  "local_stats": {
    "scope": "api_host",
    "cpu_percent": 72.5,
    "memory_percent": 81.0,
    "memory_used_mb": 6421.3,
    "memory_total_mb": 8192.0,
    "loadavg_1m": 1.42,
    "loadavg_5m": 1.27,
    "loadavg_15m": 1.11,
    "error": null
  }
}
```

## 9) Replay Tests

```bash
bash ./tools/tests/replay/test_query_probe.sh
bash ./tools/tests/replay/test_lane_probe_snapshot.sh
bash ./tools/tests/replay/test_live_stats_api.sh
python3 ./tools/tests/replay/test_query_steam_a2s.py ./tools
```
