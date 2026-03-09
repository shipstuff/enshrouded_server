#!/usr/bin/env python3
import argparse
import builtins
import contextlib
import importlib.util
import io
import json
import os
import tempfile
from pathlib import Path


def load_module(api_path: Path):
    spec = importlib.util.spec_from_file_location("live_stats_api", api_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root_dir")
    args = parser.parse_args()

    root_dir = Path(args.root_dir)
    api_path = root_dir / "services" / "api" / "live_stats_api.py"
    module = load_module(api_path)

    events = module.parse_webhook_events("up,player_add,high_latency,high_memory,high_cpu")
    assert events == {"up", "player_add", "high_latency", "high_memory", "high_cpu"}
    assert module.redact_webhook_url("https://discord.com/api/webhooks/123/secret-token") == "https://discord.com/<redacted>"
    assert module.redact_webhook_url("not-a-url") == "<redacted>"

    original_candidates = module.DEFAULT_SERVER_CONFIG_CANDIDATES
    with tempfile.TemporaryDirectory() as tmpdir:
        cwd_candidate = Path(tmpdir) / "enshrouded_server.json"
        cwd_candidate.write_text('{"name":"cwd-fixture"}', encoding="utf-8")
        module.DEFAULT_SERVER_CONFIG_CANDIDATES = (
            Path(tmpdir) / "missing.json",
            cwd_candidate,
        )
        assert module.resolve_server_config_path() == cwd_candidate
    module.DEFAULT_SERVER_CONFIG_CANDIDATES = original_candidates

    os.environ["ENSHROUDED_API_SERVER_CONFIG_PATH"] = "/tmp/explicit-config.json"
    assert module.resolve_server_config_path() == Path("/tmp/explicit-config.json")
    os.environ.pop("ENSHROUDED_API_SERVER_CONFIG_PATH", None)

    with tempfile.TemporaryDirectory() as tmpdir:
        server_config_path = Path(tmpdir) / "enshrouded_server.json"
        server_config_path.write_text('{"ip":"192.168.1.44"}', encoding="utf-8")
        assert module.resolve_probe_host(None, server_config_path) == "192.168.1.44"
        server_config_path.write_text('{"ip":"0.0.0.0"}', encoding="utf-8")
        assert module.resolve_probe_host(None, server_config_path) == "127.0.0.1"
        assert module.resolve_probe_host("10.0.0.7", server_config_path) == "10.0.0.7"
        server_config_path.write_text('{"queryPort":15639}', encoding="utf-8")
        assert module.resolve_game_port(None, server_config_path) == 15639
        server_config_path.write_text('{"queryPort":0}', encoding="utf-8")
        assert module.resolve_game_port(None, server_config_path) == 15637
        assert module.resolve_game_port(15640, server_config_path) == 15640

    try:
        module.parse_webhook_events("up,nope")
    except ValueError:
        pass
    else:
        raise AssertionError("expected invalid webhook events to fail")

    assert module.resolve_optional_float(
        parser=argparse.ArgumentParser(),
        value=12.5,
        env_name="ENSHROUDED_API_WEBHOOK_HIGH_CPU_PERCENT",
    ) == 12.5

    os.environ["ENSHROUDED_API_WEBHOOK_HIGH_CPU_PERCENT"] = "bad"
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            module.resolve_optional_float(
                parser=argparse.ArgumentParser(prog="test-live-stats-api"),
                value=None,
                env_name="ENSHROUDED_API_WEBHOOK_HIGH_CPU_PERCENT",
            )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected invalid env float to fail via argparse")
    os.environ.pop("ENSHROUDED_API_WEBHOOK_HIGH_CPU_PERCENT", None)

    sampler = module.LocalStatsSampler()
    module.build_snapshot = lambda **kwargs: {
        "live": {
            "status": "online",
            "source": "query",
            "source_lane": "game_port",
            "players_current": 1,
            "players_max": 16,
            "players_confidence": "high",
            "server_name": "fixture",
            "server_version": "1.0.0",
            "latency_ms": 42.0,
        },
        "lanes": [],
    }
    payload = module.build_stats_response(
        host="127.0.0.1",
        timeout=1.0,
        retries=2,
        lane_ports={"game_port": 32637, "steam_query": 32015},
        local_stats=sampler.sample(),
        server_config={"loaded": True, "name": "fixture", "query_port": 15637},
        startup_config={"server": {"loaded": True}, "stats_api": {"bind": "0.0.0.0"}},
    )
    assert payload["host"] == "127.0.0.1"
    assert "local_stats" in payload
    assert payload["server_config"]["name"] == "fixture"
    assert payload["local_stats"]["scope"] == "api_host"
    assert payload["startup_config"]["server"]["loaded"] is True

    payload_hidden = module.build_stats_response(
        host="127.0.0.1",
        timeout=1.0,
        retries=2,
        lane_ports={"game_port": 32637, "steam_query": 32015},
        local_stats=None,
        server_config={"loaded": False, "error": "missing"},
    )
    assert "local_stats" not in payload_hidden
    assert payload_hidden["server_config"]["loaded"] is False

    with tempfile.TemporaryDirectory() as tmpdir:
        server_config_path = Path(tmpdir) / "enshrouded_server.json"
        server_config_path.write_text(
            json.dumps(
                {
                    "name": "fixture",
                    "userGroups": [{"name": "Default", "password": "secret-pass"}],
                }
            ),
            encoding="utf-8",
        )
        startup_cfg = module.build_startup_config(
            {
                "bind": "0.0.0.0",
                "port": 8091,
                "host": "127.0.0.1",
                "timeout": 1.0,
                "retries": 2,
                "cache_ttl": 3.0,
                "lane_ports": {"game_port": 32637, "steam_query": 32015},
                "expose_local_stats": False,
                "log_events": False,
                "server_config_path": str(server_config_path),
                "webhook": {
                    "url": "https://example.invalid/hook",
                    "discord_url": "https://discord.com/api/webhooks/123/secret",
                    "timeout": 3.0,
                    "events": {"up", "player_add"},
                    "high_latency_ms": None,
                    "high_memory_percent": None,
                    "high_cpu_percent": None,
                },
            }
        )
        server_config_metadata = module.build_server_config_metadata(server_config_path)
    assert startup_cfg["server"]["loaded"] is True
    assert startup_cfg["server"]["config"]["userGroups"][0]["password"] == "<redacted>"
    assert startup_cfg["stats_api"]["webhook"]["discord_url"] == "https://discord.com/<redacted>"
    assert server_config_metadata["loaded"] is True
    assert server_config_metadata["name"] == "fixture"
    assert server_config_metadata["user_group_count"] == 1

    cfg = {
        "events": {"up", "down", "player_add", "player_remove", "high_latency", "high_memory", "high_cpu"},
        "high_latency_ms": 200.0,
        "high_memory_percent": 80.0,
        "high_cpu_percent": 70.0,
    }

    base = {
        "ts": "2026-03-06T20:00:00Z",
        "host": "127.0.0.1",
        "live": {
            "status": "unknown",
            "players_current": None,
            "players_max": None,
            "latency_ms": None,
        },
        "local_stats": {
            "scope": "api_host",
            "cpu_percent": 10.0,
            "memory_percent": 40.0,
        },
    }
    events_1, state_1 = module.evaluate_webhook_events({}, base, cfg)
    assert events_1 == []

    already_online_events, _ = module.evaluate_webhook_events({}, {
        "ts": "2026-03-06T20:00:01Z",
        "host": "127.0.0.1",
        "live": {
            "status": "online",
            "players_current": 2,
            "players_max": 16,
            "latency_ms": 150.0,
        },
        "local_stats": {
            "scope": "api_host",
            "cpu_percent": 10.0,
            "memory_percent": 40.0,
        },
    }, cfg)
    assert [event["event"] for event in already_online_events] == ["up"]
    assert already_online_events[0]["details"]["previous_status"] == "unknown"

    up = {
        "ts": "2026-03-06T20:00:03Z",
        "host": "127.0.0.1",
        "live": {
            "status": "online",
            "players_current": 2,
            "players_max": 16,
            "latency_ms": 245.0,
        },
        "local_stats": {
            "scope": "api_host",
            "cpu_percent": 72.5,
            "memory_percent": 81.0,
        },
    }
    events_2, state_2 = module.evaluate_webhook_events(state_1, up, cfg)
    assert [event["event"] for event in events_2] == ["up", "high_latency", "high_memory", "high_cpu"]

    join = {
        "ts": "2026-03-06T20:00:06Z",
        "host": "127.0.0.1",
        "live": {
            "status": "online",
            "players_current": 3,
            "players_max": 16,
            "latency_ms": 180.0,
        },
        "local_stats": {
            "scope": "api_host",
            "cpu_percent": 65.0,
            "memory_percent": 70.0,
        },
    }
    events_3, state_3 = module.evaluate_webhook_events(state_2, join, cfg)
    assert [event["event"] for event in events_3] == ["player_add"]
    assert events_3[0]["details"]["delta"] == 1

    leave = {
        "ts": "2026-03-06T20:00:09Z",
        "host": "127.0.0.1",
        "live": {
            "status": "online",
            "players_current": 1,
            "players_max": 16,
            "latency_ms": 150.0,
        },
        "local_stats": {
            "scope": "api_host",
            "cpu_percent": 40.0,
            "memory_percent": 50.0,
        },
    }
    events_4, state_4 = module.evaluate_webhook_events(state_3, leave, cfg)
    assert [event["event"] for event in events_4] == ["player_remove"]
    assert events_4[0]["details"]["delta"] == 2

    down = {
        "ts": "2026-03-06T20:00:12Z",
        "host": "127.0.0.1",
        "live": {
            "status": "unknown",
            "players_current": None,
            "players_max": None,
            "latency_ms": None,
        },
        "local_stats": {
            "scope": "api_host",
            "cpu_percent": 20.0,
            "memory_percent": 35.0,
        },
    }
    events_5, state_5 = module.evaluate_webhook_events(state_4, down, cfg)
    assert [event["event"] for event in events_5] == ["down"]
    assert state_5["online"] is False

    recover = {
        "ts": "2026-03-06T20:00:15Z",
        "host": "127.0.0.1",
        "live": {
            "status": "online",
            "players_current": 1,
            "players_max": 16,
            "latency_ms": 260.0,
        },
        "local_stats": {
            "scope": "api_host",
            "cpu_percent": 71.0,
            "memory_percent": 83.0,
        },
    }
    events_6, state_6 = module.evaluate_webhook_events(state_5, recover, cfg)
    assert [event["event"] for event in events_6] == ["up", "high_latency", "high_memory", "high_cpu"]

    cooldown = {
        "ts": "2026-03-06T20:00:18Z",
        "host": "127.0.0.1",
        "live": {
            "status": "online",
            "players_current": 1,
            "players_max": 16,
            "latency_ms": 150.0,
        },
        "local_stats": {
            "scope": "api_host",
            "cpu_percent": 40.0,
            "memory_percent": 50.0,
        },
    }
    events_7, state_7 = module.evaluate_webhook_events(state_6, cooldown, cfg)
    assert events_7 == []

    spike_again = {
        "ts": "2026-03-06T20:00:21Z",
        "host": "127.0.0.1",
        "live": {
            "status": "online",
            "players_current": 1,
            "players_max": 16,
            "latency_ms": 275.0,
        },
        "local_stats": {
            "scope": "api_host",
            "cpu_percent": 75.0,
            "memory_percent": 85.0,
        },
    }
    events_8, _ = module.evaluate_webhook_events(state_7, spike_again, cfg)
    assert [event["event"] for event in events_8] == ["high_latency", "high_memory", "high_cpu"]

    discord_body = module.build_discord_webhook_payload(events_3[0])
    assert "Enshrouded `player_add`" in discord_body["content"]
    assert discord_body["allowed_mentions"] == {"parse": []}
    assert discord_body["embeds"][0]["title"] == "Enshrouded player_add"
    assert discord_body["embeds"][0]["color"] == module.discord_event_color("player_add")
    embed_fields = {field["name"]: field["value"] for field in discord_body["embeds"][0]["fields"]}
    assert embed_fields["Host"] == "127.0.0.1"
    assert embed_fields["Players"] == "2 -> 3 (delta +1)"

    class FakeResponse:
        def __init__(self, status: int, body: bytes) -> None:
            self.status = status
            self._body = body

        def read(self) -> bytes:
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    captured_requests = []

    def fake_urlopen(request, timeout):
        captured_requests.append(
            {
                "url": request.full_url,
                "timeout": timeout,
                "body": json.loads(request.data.decode("utf-8")),
                "headers": dict(request.header_items()),
            }
        )
        return FakeResponse(204, b"")

    original_urlopen = module.urllib.request.urlopen
    try:
        module.urllib.request.urlopen = fake_urlopen
        json_result = module.post_webhook(
            "https://generic.example/webhook",
            3.0,
            events_3[0],
            kind="json",
        )
        discord_result = module.post_webhook(
            "https://discord.example/webhook",
            3.0,
            events_3[0],
            kind="discord",
        )
    finally:
        module.urllib.request.urlopen = original_urlopen
    assert json_result["status"] == 204
    assert discord_result["status"] == 204
    assert captured_requests[0]["url"] == "https://generic.example/webhook"
    assert captured_requests[0]["body"]["event"] == "player_add"
    assert captured_requests[0]["headers"]["User-agent"] == "live-stats-api/1.0"
    assert captured_requests[1]["url"] == "https://discord.example/webhook"
    assert captured_requests[1]["body"]["allowed_mentions"] == {"parse": []}
    assert "Enshrouded `player_add`" in captured_requests[1]["body"]["content"]
    assert captured_requests[1]["body"]["embeds"][0]["title"] == "Enshrouded player_add"
    assert captured_requests[1]["headers"]["User-agent"] == "live-stats-api/1.0"

    handler = module.Handler.__new__(module.Handler)
    assert handler.version_string() == "live-stats-api/1.0"

    class Capture:
        def __init__(self) -> None:
            self.items = []

        def __call__(self, line: str, flush: bool = False) -> None:
            self.items.append((line, flush))

    capture = Capture()
    original_print = builtins.print
    try:
        builtins.print = capture
        module.Handler.config = {"log_events": True, "webhook": dict(cfg, url=None, timeout=1.0)}
        module.Handler.webhook_state = state_1
        module.Handler._dispatch_webhook_events(up)
    finally:
        builtins.print = original_print
    assert len(capture.items) == 4
    first_log = json.loads(capture.items[0][0])
    assert first_log["event_log"]["event"] == "up"

    print(json.dumps({"ok": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
