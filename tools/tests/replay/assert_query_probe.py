#!/usr/bin/env python3
import json
import sys


def main() -> int:
    kind = sys.argv[1]
    with open(sys.argv[2], "r", encoding="utf-8") as handle:
        data = json.load(handle)

    assert data["ok"] is True
    if kind == "info":
        assert data["players_current"] == 1
        assert data["players_max"] == 16
        assert data["query_port_reported"] == 27015
        assert data["server_name"] == "Enshrouded Test Server"
    elif kind == "player":
        assert data["player_count"] == 2
        assert data["players"][0]["name"] == ""
        assert data["players"][1]["name"] == "PanTester"
    elif kind == "rules":
        assert data["rule_count"] == 3
        assert data["rules"][0] == {"name": "game_build", "value": "0.0.15.0"}
    else:
        raise AssertionError(f"unknown kind: {kind}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
