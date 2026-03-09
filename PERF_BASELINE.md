# Enshrouded Performance Baseline

Captured: 2026-03-04 19:26-19:27 PST
Environment: node spec `16GB RAM`, `4-core Intel N95`, `Kubernetes v1.34`; pod `games/enshrouded-0`
Workload note: sampled during live play (operator indicated 2 connected players).

## Sampling method

- 6 samples, 15s interval (~90s window)
- Metrics captured each sample:
  - `kubectl top pod -n games enshrouded-0 --containers`
  - `kubectl top node fresno-west-1`
  - `ps` inside pod for `enshrouded_server.exe`, `xalia.exe`, `wineserver`
  - host CPU frequency snapshot + thermal throttle counters

## Baseline results

| Metric | Value |
|---|---|
| Pod CPU | 2289m to 2312m (avg ~2300m) |
| Pod Memory | 1643 MiB (stable) |
| Node CPU | 2335m to 2410m (68-70%, avg ~2367m) |
| Node Memory | ~2990-3004 MiB (20%) |
| `enshrouded_server.exe` CPU | ~244% (stable) |
| `xalia.exe` CPU | ~2.5-2.6% |
| `wineserver` CPU | ~0.4% |
| CPU freq snapshot | mostly ~2.69 GHz across cores |
| `core_throttle_count` | 0 on cpu0-3 |
| `package_throttle_count` | 0 on cpu0-3 |

## Interpretation

- No thermal throttling observed in counters.
- CPU policy is aggressive max-performance (`performance` governor + pstate floor/cap 100).
- This is the reference baseline for first tuning experiment.

## Next experiment (planned)

1. Change: disable Xalia (`PROTON_USE_XALIA=0`).
2. Re-run exact same sampler and compare deltas against this baseline.

## Experiment 1 (executed): `PROTON_USE_XALIA=0`

Status: incomplete comparison (workload mismatch after restart).

### Post-change sample summary (6x, 15s)

| Metric | Value |
|---|---|
| Pod CPU | 497m to 502m (avg ~500m) |
| Pod Memory | 1155 MiB (stable) |
| Node CPU | 559m to 572m (16%) |
| Node Memory | ~2500-2514 MiB (16%) |
| `enshrouded_server.exe` CPU | ~50.6-52.8% |
| `xalia.exe` CPU | not present (process removed) |
| `wineserver` CPU | ~0.5-0.8% |
| `core_throttle_count` | 0 on cpu0-3 |
| `package_throttle_count` | 0 on cpu0-3 |

### Interpretation

- `xalia.exe` was successfully removed.
- CPU and memory dropped sharply vs baseline, indicating a different gameplay load than the baseline capture.
- Re-run required with controlled player count/session activity for valid A/B conclusion.

## Experiment 1 (re-run with active player): `PROTON_USE_XALIA=0`

Captured: 2026-03-04 20:05-20:06 PST
Workload note: at least 1 connected player (operator-confirmed).

### Post-change sample summary (6x, 15s)

| Metric | Value |
|---|---|
| Pod CPU | 2107m to 2218m (avg ~2145m) |
| Pod Memory | 1488 MiB (stable) |
| Node CPU | 2169m to 2291m (63-67%, avg ~2207m) |
| Node Memory | ~2835-2861 MiB (19%) |
| `xalia.exe` process | not present |
| `core_throttle_count` | 0 on cpu0-3 |
| `package_throttle_count` | 0 on cpu0-3 |

### Delta vs original baseline

| Metric | Baseline | Re-run | Delta |
|---|---|---|---|
| Pod CPU avg | ~2300m | ~2145m | ~-6.7% |
| Pod Memory | 1643 MiB | 1488 MiB | ~-9.4% |
| Node CPU avg | ~2367m | ~2207m | ~-6.8% |

### Interpretation

- This run is directionally better than baseline and still shows no thermal throttling.
- Because player count/activity did not exactly match the original baseline window, treat these deltas as provisional.

## Experiment 1 (re-run, high-load session): `PROTON_USE_XALIA=0`

Captured: 2026-03-04 20:09-20:10 PST
Workload note: sampled during active multiplayer session ("2-player-like" load based on CPU profile).

### Post-change sample summary (6x, 15s)

| Metric | Value |
|---|---|
| Pod CPU | 2193m to 2253m (avg ~2214m) |
| Pod Memory | 1503 MiB (stable) |
| Node CPU | 2253m to 2318m (66-68%, avg ~2280m) |
| Node Memory | ~2853-2860 MiB (19%) |
| `xalia.exe` process | not present |
| `core_throttle_count` | 0 on cpu0-3 |
| `package_throttle_count` | 0 on cpu0-3 |

### Delta vs original baseline

| Metric | Baseline | Re-run | Delta |
|---|---|---|---|
| Pod CPU avg | ~2300m | ~2214m | ~-3.7% |
| Pod Memory | 1643 MiB | 1503 MiB | ~-8.5% |
| Node CPU avg | ~2367m | ~2280m | ~-3.7% |

### Interpretation

- With `PROTON_USE_XALIA=0`, the high-load re-run still trends lower than original baseline.
- Thermal throttle counters remain zero.
- This is a better A/B candidate than the prior low-load rerun, though exact player activity still influences final numbers.

## Experiment 1 (confirmed): `PROTON_USE_XALIA=0` with 2 players

Captured: 2026-03-04 20:12-20:13 PST
Workload note: operator-confirmed 2 connected players.

### Post-change sample summary (6x, 15s)

| Metric | Value |
|---|---|
| Pod CPU | 2195m to 2233m (avg ~2212m) |
| Pod Memory | 1503-1504 MiB |
| Node CPU | 2239m to 2298m (65-67%, avg ~2278m) |
| Node Memory | ~2850-2861 MiB (19%) |
| `xalia.exe` process | not present |
| `core_throttle_count` | 0 on cpu0-3 |
| `package_throttle_count` | 0 on cpu0-3 |

### Delta vs original baseline

| Metric | Baseline | Confirmed re-run | Delta |
|---|---|---|---|
| Pod CPU avg | ~2300m | ~2212m | ~-3.8% |
| Pod Memory | 1643 MiB | ~1503 MiB | ~-8.5% |
| Node CPU avg | ~2367m | ~2278m | ~-3.8% |

## Experiment 2: `GAME_SETTINGS_PRESET=Relaxed` (with `PROTON_USE_XALIA=0`)

Captured: 2026-03-04 20:37-20:38 PST
Workload note: active multiplayer session.

### Post-change sample summary (6x, 15s)

| Metric | Value |
|---|---|
| Pod CPU | 2081m to 2242m (avg ~2187m) |
| Pod Memory | 1416-1420 MiB |
| Node CPU | 2066m to 2317m (60-68%, avg ~2262m) |
| Node Memory | ~2769-2783 MiB (18%) |
| `xalia.exe` process | not present |
| `core_throttle_count` | 0 on cpu0-3 |
| `package_throttle_count` | 0 on cpu0-3 |

### Delta vs original baseline

| Metric | Baseline | Relaxed run | Delta |
|---|---|---|---|
| Pod CPU avg | ~2300m | ~2187m | ~-4.9% |
| Pod Memory | 1643 MiB | ~1418 MiB | ~-13.7% |
| Node CPU avg | ~2367m | ~2262m | ~-4.4% |

### Delta vs Experiment 1 confirmed (`PROTON_USE_XALIA=0`, Default preset)

| Metric | Exp 1 confirmed | Relaxed run | Delta |
|---|---|---|---|
| Pod CPU avg | ~2212m | ~2187m | ~-1.1% |
| Pod Memory | ~1503 MiB | ~1418 MiB | ~-5.7% |
| Node CPU avg | ~2278m | ~2262m | ~-0.7% |

### Interpretation

- Relaxed preset shows only a small additional CPU improvement over xalia-off + Default in this short run.
- Memory dropped more noticeably.
- Net: gameplay compromise may not be worth it if CPU reduction is the only goal.

## Operational note: lowering slots when possible

Configuration change:
- `SERVER_SLOTS=4` instead of default `16`

### Qualitative observation

- We did not observe a large CPU difference from this change in short samples.
- Gameplay was noticeably smoother after lowering slots.
- "Server overloaded" messages stopped appearing after reducing slots from 16 to 4.

This should be treated as a qualitative gameplay/stability win until we capture a controlled A/B run focused specifically on slot-count changes.
