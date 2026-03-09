#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import time
from typing import Dict, List, Optional

from query_steam_a2s import A2S_QUERY_TYPES, decode_hex_file, query_a2s_bundle, summarize_bundle

LANE_DEFAULTS = {
    "game_port_1": 15636,
    "game_port_2": 15637,
    "steam_query": 27015,
}

PRIMARY_ORDER = ["game_port_2", "game_port_1", "steam_query"]
LANES = ["game_port_1", "game_port_2", "steam_query"]
EMPTY_LANE = {
    "players_current": None,
    "players_max": None,
    "server_name": None,
    "version": None,
}


def _fixture_bundle(fixture_dir: str) -> Dict:
    base = Path(fixture_dir)
    return {
        query_type: decode_hex_file(str(base / f"a2s-{query_type}-response.hex"), query_type=query_type)
        for query_type in A2S_QUERY_TYPES
    }


def _format_lane_result(lane: str, port: int, target: str, raw_bundle: Dict) -> Dict:
    a2s = summarize_bundle(raw_bundle)
    out = dict(a2s["info"])
    out.update({"lane": lane, "target": target, "port": port, "ok": bool(out.get("ok"))})
    if not out["ok"]:
        out.update(EMPTY_LANE)
    out["a2s"] = a2s
    out["player_count"] = a2s["player"].get("player_count")
    out["rule_count"] = a2s["rules"].get("rule_count")
    return out


def build_snapshot(
    host: str,
    timeout: float,
    retries: int,
    lane_ports: Dict[str, int],
    fixture_lane: Optional[str] = None,
    fixture_dir: Optional[str] = None,
) -> Dict:
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    lanes: List[Dict] = []

    for lane in LANES:
        port = lane_ports[lane]
        if fixture_lane and fixture_dir:
            if lane == fixture_lane:
                result = _format_lane_result(
                    lane=lane,
                    port=port,
                    target=f"fixture:{port}",
                    raw_bundle=_fixture_bundle(fixture_dir),
                )
            else:
                result = {
                    "lane": lane,
                    "target": f"fixture-skip:{port}",
                    "port": port,
                    "ok": False,
                    "error": "fixture mode: lane not sampled",
                    "a2s": {
                        query_type: {
                            "ok": False,
                            "error": "fixture mode: lane not sampled",
                        }
                        for query_type in A2S_QUERY_TYPES
                    },
                    "player_count": None,
                    "rule_count": None,
                    **EMPTY_LANE,
                }
        else:
            result = _format_lane_result(
                lane=lane,
                port=port,
                target=f"{host}:{port}",
                raw_bundle=query_a2s_bundle(host=host, port=port, timeout=timeout, retries=retries),
            )
        lanes.append(result)

    primary = next(
        (
            lane
            for lane_name in PRIMARY_ORDER
            for lane in lanes
            if lane["lane"] == lane_name and lane.get("ok")
        ),
        None,
    )

    if primary:
        live = {
            "status": "online",
            "source": "query",
            "source_lane": primary["lane"],
            "players_current": primary.get("players_current"),
            "players_max": primary.get("players_max"),
            "players_confidence": "high",
            "server_name": primary.get("server_name"),
            "server_version": primary.get("version"),
            "latency_ms": primary.get("latency_ms"),
            "a2s_player_count": primary.get("player_count"),
            "a2s_rule_count": primary.get("rule_count"),
        }
    else:
        live = {
            "status": "unknown",
            "source": "query",
            "source_lane": None,
            "players_current": None,
            "players_max": None,
            "players_confidence": "low",
            "server_name": None,
            "server_version": None,
            "latency_ms": None,
            "a2s_player_count": None,
            "a2s_rule_count": None,
        }

    return {
        "ts": ts,
        "host": host,
        "lanes": lanes,
        "live": live,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Lane-aware Enshrouded query snapshot runner.")
    parser.add_argument("--host", default="127.0.0.1", help="Target host")
    parser.add_argument("--timeout", type=float, default=1.0, help="UDP timeout seconds")
    parser.add_argument("--retries", type=int, default=2, help="Retries per lane")
    parser.add_argument("--game-port-1", type=int, default=LANE_DEFAULTS["game_port_1"], help="UDP port for 15636 lane")
    parser.add_argument("--game-port-2", type=int, default=LANE_DEFAULTS["game_port_2"], help="UDP port for 15637 lane")
    parser.add_argument("--steam-query-port", type=int, default=LANE_DEFAULTS["steam_query"], help="UDP port for 27015 lane")
    parser.add_argument("--fixture-lane", choices=["game_port_1", "game_port_2", "steam_query"], help="Use fixture decode for one lane")
    parser.add_argument("--fixture-dir", help="Fixture directory containing a2s-info/player/rules-response.hex (requires --fixture-lane)")
    parser.add_argument("--json-out", help="Optional output path")
    parser.add_argument("--summary", action="store_true", help="Print live+lane status summary")
    args = parser.parse_args()

    if bool(args.fixture_lane) != bool(args.fixture_dir):
        raise SystemExit("--fixture-lane and --fixture-dir must be used together")

    lane_ports = {
        "game_port_1": args.game_port_1,
        "game_port_2": args.game_port_2,
        "steam_query": args.steam_query_port,
    }

    snapshot = build_snapshot(
        host=args.host,
        timeout=args.timeout,
        retries=args.retries,
        lane_ports=lane_ports,
        fixture_lane=args.fixture_lane,
        fixture_dir=args.fixture_dir,
    )

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2)

    if args.summary:
        summary = {
            "ts": snapshot["ts"],
            "host": snapshot["host"],
            "live": snapshot["live"],
            "lane_status": {lane["lane"]: {"ok": lane["ok"], "error": lane.get("error")} for lane in snapshot["lanes"]},
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
