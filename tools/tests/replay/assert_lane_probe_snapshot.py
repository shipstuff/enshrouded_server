#!/usr/bin/env python3
import json
import sys


def main() -> int:
    with open(sys.argv[1], "r", encoding="utf-8") as handle:
        data = json.load(handle)

    assert data["live"]["status"] == "online"
    assert data["live"]["source"] == "query"
    assert data["live"]["source_lane"] == "game_port_2"
    assert data["live"]["players_current"] == 1
    assert data["live"]["a2s_player_count"] == 2
    assert data["live"]["a2s_rule_count"] == 3
    assert data["lane_status"]["game_port_2"]["ok"] is True
    assert data["lane_status"]["game_port_1"]["ok"] is False
    assert data["lane_status"]["steam_query"]["ok"] is False
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
