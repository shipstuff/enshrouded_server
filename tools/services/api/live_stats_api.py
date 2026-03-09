#!/usr/bin/env python3
import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

HERE = Path(__file__).resolve()
TOOLS_ROOT = HERE.parents[2]
PROBES_DIR = TOOLS_ROOT / "probes"
STATIC_DIR = HERE.parent / "static"
INDEX_HTML_PATH = STATIC_DIR / "index.html"
USER_AGENT = "live-stats-api/1.0"
DEFAULT_SERVER_CONFIG_PATH = Path(os.getenv("ENSHROUDED_API_SERVER_CONFIG_PATH", "/home/steam/enshrouded/enshrouded_server.json"))
DEFAULT_WEBHOOK_EVENTS = {
    "up",
    "down",
    "player_add",
    "player_remove",
    "high_latency",
    "high_memory",
    "high_cpu",
}
THRESHOLD_EVENTS = (
    ("high_latency", "high_latency_ms", "high_latency_active", "threshold_ms", "value_ms", "latency_ms"),
    ("high_memory", "high_memory_percent", "high_memory_active", "threshold_percent", "value_percent", "memory_percent"),
    ("high_cpu", "high_cpu_percent", "high_cpu_active", "threshold_percent", "value_percent", "cpu_percent"),
)
sys.path.insert(0, str(PROBES_DIR))

from lane_probe_snapshot import LANE_DEFAULTS, build_snapshot  # noqa: E402


def log_stderr(message: str, **fields) -> None:
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload = {
        "ts": ts,
        "message": message,
    }
    payload.update(fields)
    print(f"[{ts}] {json.dumps(payload, sort_keys=True)}", file=sys.stderr, flush=True)


def redact_webhook_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return "<redacted>"
    if not parsed.scheme or not parsed.netloc:
        return "<redacted>"
    return f"{parsed.scheme}://{parsed.netloc}/<redacted>"


def redact_value(key: str, value: Any) -> Any:
    lowered = key.lower()
    if any(token in lowered for token in ("password", "token", "secret")):
        return "<redacted>" if value not in (None, "") else value
    return value


def redact_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: redact_mapping(redact_value(key, nested)) for key, nested in value.items()}
    if isinstance(value, list):
        return [redact_mapping(item) for item in value]
    return value


def build_startup_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    webhook_cfg = cfg.get("webhook", {})
    server_config_path = Path(cfg.get("server_config_path", DEFAULT_SERVER_CONFIG_PATH))
    server = {
        "config_path": str(server_config_path),
        "loaded": False,
        "config": None,
        "error": None,
    }
    try:
        server["config"] = redact_mapping(json.loads(server_config_path.read_text(encoding="utf-8")))
        server["loaded"] = True
    except FileNotFoundError:
        server["error"] = f"config not found at {server_config_path}"
    except (OSError, json.JSONDecodeError) as exc:
        server["error"] = str(exc)

    stats_api = {
        "bind": cfg["bind"],
        "port": cfg["port"],
        "host": cfg["host"],
        "timeout": cfg["timeout"],
        "retries": cfg["retries"],
        "cache_ttl": cfg["cache_ttl"],
        "lane_ports": cfg["lane_ports"],
        "expose_local_stats": cfg.get("expose_local_stats", False),
        "log_events": cfg.get("log_events", False),
        "webhook": {
            "url": redact_webhook_url(webhook_cfg["url"]) if webhook_cfg.get("url") else None,
            "discord_url": redact_webhook_url(webhook_cfg["discord_url"]) if webhook_cfg.get("discord_url") else None,
            "timeout": webhook_cfg.get("timeout"),
            "events": sorted(webhook_cfg.get("events", [])),
            "high_latency_ms": webhook_cfg.get("high_latency_ms"),
            "high_memory_percent": webhook_cfg.get("high_memory_percent"),
            "high_cpu_percent": webhook_cfg.get("high_cpu_percent"),
        },
    }

    return {
        "server": server,
        "stats_api": redact_mapping(stats_api),
    }


def format_metric_value(value: Any, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        text = f"{value:.2f}".rstrip("0").rstrip(".")
        return f"{text}{suffix}"
    return f"{value}{suffix}"


def build_discord_lines(event_payload: Dict) -> List[str]:
    event = event_payload["event"]
    details = event_payload.get("details") or {}
    live = event_payload.get("live") or {}
    local_stats = event_payload.get("local_stats") or {}

    lines = [
        f"**Enshrouded `{event}`**",
        f"Host: `{event_payload['host']}`",
        f"Timestamp: `{event_payload['ts']}`",
    ]

    if event in {"up", "down"}:
        lines.append(
            "State: "
            f"{details.get('previous_status', 'n/a')} -> {details.get('current_status', 'n/a')}"
        )
    elif event in {"player_add", "player_remove"}:
        direction = "+" if event == "player_add" else "-"
        lines.append(
            "Players: "
            f"{format_metric_value(details.get('players_previous'))} -> "
            f"{format_metric_value(details.get('players_current'))} "
            f"(delta {direction}{format_metric_value(details.get('delta'))})"
        )
    elif event == "high_latency":
        lines.append(
            "Latency: "
            f"{format_metric_value(details.get('value_ms'), ' ms')} "
            f"(threshold {format_metric_value(details.get('threshold_ms'), ' ms')})"
        )
    elif event == "high_memory":
        lines.append(
            "API host memory: "
            f"{format_metric_value(details.get('value_percent'), '%')} "
            f"(threshold {format_metric_value(details.get('threshold_percent'), '%')})"
        )
    elif event == "high_cpu":
        lines.append(
            "API host CPU: "
            f"{format_metric_value(details.get('value_percent'), '%')} "
            f"(threshold {format_metric_value(details.get('threshold_percent'), '%')})"
        )

    if live:
        lines.append(f"Live: {live.get('status', 'n/a')} via {live.get('source_lane', 'n/a')}")
        if live.get("players_current") is not None or live.get("players_max") is not None:
            lines.append(
                "Capacity: "
                f"{format_metric_value(live.get('players_current'))}/{format_metric_value(live.get('players_max'))}"
            )
        if live.get("latency_ms") is not None:
            lines.append(f"Observed latency: {format_metric_value(live.get('latency_ms'), ' ms')}")
        if live.get("server_name"):
            server_line = f"Server: {live['server_name']}"
            if live.get("server_version"):
                server_line += f" ({live['server_version']})"
            lines.append(server_line)

    if local_stats and (
        local_stats.get("cpu_percent") is not None or local_stats.get("memory_percent") is not None
    ):
        lines.append(
            "API host stats: "
            f"cpu={format_metric_value(local_stats.get('cpu_percent'), '%')} "
            f"memory={format_metric_value(local_stats.get('memory_percent'), '%')}"
        )
    return lines


def discord_event_color(event: str) -> int:
    return {
        "up": 0x2ECC71,
        "down": 0xE74C3C,
        "player_add": 0x3498DB,
        "player_remove": 0xF39C12,
        "high_latency": 0xE67E22,
        "high_memory": 0xC0392B,
        "high_cpu": 0x8E44AD,
    }.get(event, 0x95A5A6)


def build_discord_embed_fields(event_payload: Dict) -> List[Dict[str, Any]]:
    event = event_payload["event"]
    details = event_payload.get("details") or {}
    live = event_payload.get("live") or {}
    local_stats = event_payload.get("local_stats") or {}
    fields: List[Dict[str, Any]] = [
        {"name": "Event", "value": event, "inline": True},
        {"name": "Host", "value": event_payload["host"], "inline": True},
    ]

    if event in {"up", "down"}:
        fields.append(
            {
                "name": "State",
                "value": f"{details.get('previous_status', 'n/a')} -> {details.get('current_status', 'n/a')}",
                "inline": True,
            }
        )
    elif event in {"player_add", "player_remove"}:
        direction = "+" if event == "player_add" else "-"
        fields.append(
            {
                "name": "Players",
                "value": (
                    f"{format_metric_value(details.get('players_previous'))} -> "
                    f"{format_metric_value(details.get('players_current'))} "
                    f"(delta {direction}{format_metric_value(details.get('delta'))})"
                ),
                "inline": True,
            }
        )
    elif event == "high_latency":
        fields.append(
            {
                "name": "Latency",
                "value": (
                    f"{format_metric_value(details.get('value_ms'), ' ms')} "
                    f"(threshold {format_metric_value(details.get('threshold_ms'), ' ms')})"
                ),
                "inline": True,
            }
        )
    elif event in {"high_memory", "high_cpu"}:
        metric_name = "Memory" if event == "high_memory" else "CPU"
        fields.append(
            {
                "name": f"API Host {metric_name}",
                "value": (
                    f"{format_metric_value(details.get('value_percent'), '%')} "
                    f"(threshold {format_metric_value(details.get('threshold_percent'), '%')})"
                ),
                "inline": True,
            }
        )

    if live:
        fields.append(
            {
                "name": "Live Status",
                "value": f"{live.get('status', 'n/a')} via {live.get('source_lane', 'n/a')}",
                "inline": True,
            }
        )
        if live.get("players_current") is not None or live.get("players_max") is not None:
            fields.append(
                {
                    "name": "Capacity",
                    "value": f"{format_metric_value(live.get('players_current'))}/{format_metric_value(live.get('players_max'))}",
                    "inline": True,
                }
            )
        if live.get("latency_ms") is not None:
            fields.append(
                {
                    "name": "Observed Latency",
                    "value": format_metric_value(live.get("latency_ms"), " ms"),
                    "inline": True,
                }
            )
        if live.get("server_name"):
            server_value = live["server_name"]
            if live.get("server_version"):
                server_value += f" ({live['server_version']})"
            fields.append({"name": "Server", "value": server_value, "inline": False})

    if local_stats and (
        local_stats.get("cpu_percent") is not None or local_stats.get("memory_percent") is not None
    ):
        fields.append(
            {
                "name": "API Host Stats",
                "value": (
                    f"cpu={format_metric_value(local_stats.get('cpu_percent'), '%')} "
                    f"memory={format_metric_value(local_stats.get('memory_percent'), '%')}"
                ),
                "inline": False,
            }
        )
    return fields[:25]


def build_discord_webhook_payload(event_payload: Dict) -> Dict[str, Any]:
    event = event_payload["event"]
    summary = build_discord_lines(event_payload)
    embed = {
        "title": f"Enshrouded {event}",
        "color": discord_event_color(event),
        "timestamp": event_payload["ts"],
        "fields": build_discord_embed_fields(event_payload),
        "footer": {"text": "Enshrouded live stats webhook"},
    }
    if len(summary) > 3:
        embed["description"] = summary[3]
    return {
        "content": f"Enshrouded `{event}` on `{event_payload['host']}`",
        "allowed_mentions": {"parse": []},
        "embeds": [embed],
    }


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_text(name: str) -> Optional[str]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    return raw.strip()


def resolve_optional_float(parser: argparse.ArgumentParser, value: Optional[float], env_name: str) -> Optional[float]:
    if value is not None:
        return value
    raw = env_text(env_name)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        parser.error(f"invalid float in {env_name}: {raw!r}")


class LocalStatsSampler:
    def __init__(self) -> None:
        self._previous_cpu: Optional[Tuple[int, int]] = None

    def _sample_cpu_percent(self) -> Tuple[Optional[float], Optional[str]]:
        if not sys.platform.startswith("linux"):
            return None, "local cpu stats only supported on linux"

        with open("/proc/stat", "r", encoding="utf-8") as handle:
            first = handle.readline().strip().split()
        if len(first) < 6 or first[0] != "cpu":
            return None, "unexpected /proc/stat format"

        values = [int(part) for part in first[1:]]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values)

        percent = None
        if self._previous_cpu is not None:
            prev_total, prev_idle = self._previous_cpu
            total_delta = total - prev_total
            idle_delta = idle - prev_idle
            if total_delta > 0:
                percent = max(0.0, min(100.0, 100.0 * (1.0 - (idle_delta / total_delta))))

        self._previous_cpu = (total, idle)
        return percent, None

    def sample(self) -> Dict:
        out = {
            "scope": "api_host",
            "cpu_percent": None,
            "memory_percent": None,
            "memory_used_mb": None,
            "memory_total_mb": None,
            "loadavg_1m": None,
            "loadavg_5m": None,
            "loadavg_15m": None,
            "error": None,
        }

        cpu_percent, cpu_error = self._sample_cpu_percent()
        out["cpu_percent"] = round(cpu_percent, 2) if cpu_percent is not None else None

        try:
            meminfo = {}
            with open("/proc/meminfo", "r", encoding="utf-8") as handle:
                for line in handle:
                    if ":" not in line:
                        continue
                    key, value = line.split(":", 1)
                    meminfo[key] = int(value.strip().split()[0])
            mem_total_kib = meminfo["MemTotal"]
            mem_available_kib = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
            mem_used_kib = max(mem_total_kib - mem_available_kib, 0)
            out["memory_total_mb"] = round(mem_total_kib / 1024.0, 2)
            out["memory_used_mb"] = round(mem_used_kib / 1024.0, 2)
            out["memory_percent"] = round((mem_used_kib / mem_total_kib) * 100.0, 2)
        except (FileNotFoundError, KeyError, ValueError) as exc:
            out["error"] = str(exc)

        try:
            load_1m, load_5m, load_15m = os.getloadavg()
            out["loadavg_1m"] = round(load_1m, 2)
            out["loadavg_5m"] = round(load_5m, 2)
            out["loadavg_15m"] = round(load_15m, 2)
        except OSError as exc:
            out["error"] = out["error"] or str(exc)

        if cpu_error:
            out["error"] = out["error"] or cpu_error

        return out


def build_stats_response(
    host: str,
    timeout: float,
    retries: int,
    lane_ports: Dict[str, int],
    local_stats: Optional[Dict] = None,
    startup_config: Optional[Dict[str, Any]] = None,
) -> Dict:
    snap = build_snapshot(host=host, timeout=timeout, retries=retries, lane_ports=lane_ports)
    payload = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": host,
        "lane_ports": lane_ports,
        "live": snap["live"],
        "lanes": snap["lanes"],
    }
    if local_stats is not None:
        payload["local_stats"] = local_stats
    if startup_config is not None:
        payload["startup_config"] = startup_config
    return payload


def parse_webhook_events(raw: Optional[str]) -> Set[str]:
    if raw is None or raw.strip() == "":
        return set(DEFAULT_WEBHOOK_EVENTS)
    events = {item.strip().lower() for item in raw.split(",") if item.strip()}
    unknown = sorted(events - DEFAULT_WEBHOOK_EVENTS)
    if unknown:
        raise ValueError(f"unknown webhook events: {', '.join(unknown)}")
    return events


def _event_payload(event: str, current: Dict, details: Dict) -> Dict:
    return {
        "event": event,
        "ts": current["ts"],
        "host": current["host"],
        "details": details,
        "live": current.get("live"),
        "local_stats": current.get("local_stats"),
    }


def evaluate_webhook_events(previous_state: Dict, current: Dict, webhook_cfg: Dict) -> Tuple[List[Dict], Dict]:
    next_state = dict(previous_state or {})
    events: List[Dict] = []
    enabled_events = webhook_cfg.get("events", set())
    live = current.get("live") or {}
    local_stats = current.get("local_stats") or {}

    online = live.get("status") == "online"
    previous_online = next_state.get("online")
    players_current = live.get("players_current")

    if previous_online is None and online and "up" in enabled_events:
        events.append(
            _event_payload(
                "up",
                current,
                {
                    "previous_status": "unknown",
                    "current_status": live.get("status"),
                },
            )
        )
    elif previous_online is False and online and "up" in enabled_events:
        events.append(
            _event_payload(
                "up",
                current,
                {
                    "previous_status": "down",
                    "current_status": live.get("status"),
                },
            )
        )
    if previous_online is True and not online and "down" in enabled_events:
        events.append(
            _event_payload(
                "down",
                current,
                {
                    "previous_status": "online",
                    "current_status": live.get("status"),
                },
            )
        )

    previous_players = next_state.get("players_current")
    if online and previous_online is True and isinstance(previous_players, int) and isinstance(players_current, int):
        delta = players_current - previous_players
        if delta > 0 and "player_add" in enabled_events:
            events.append(
                _event_payload(
                    "player_add",
                    current,
                    {
                        "delta": delta,
                        "players_previous": previous_players,
                        "players_current": players_current,
                    },
                )
            )
        elif delta < 0 and "player_remove" in enabled_events:
            events.append(
                _event_payload(
                    "player_remove",
                    current,
                    {
                        "delta": abs(delta),
                        "players_previous": previous_players,
                        "players_current": players_current,
                    },
                )
            )

    next_state["online"] = online
    next_state["players_current"] = players_current if isinstance(players_current, int) else None

    values = {
        "latency_ms": live.get("latency_ms"),
        "memory_percent": local_stats.get("memory_percent"),
        "cpu_percent": local_stats.get("cpu_percent"),
    }
    for event, threshold_key, state_key, detail_threshold_key, detail_value_key, value_key in THRESHOLD_EVENTS:
        threshold = webhook_cfg.get(threshold_key)
        value = values[value_key]
        active = bool(threshold is not None and value is not None and value >= threshold)
        if active and not next_state.get(state_key, False) and event in enabled_events:
            events.append(
                _event_payload(
                    event,
                    current,
                    {
                        detail_threshold_key: threshold,
                        detail_value_key: value,
                    },
                )
            )
        next_state[state_key] = active
    return events, next_state


def post_webhook(url: str, timeout: float, payload: Dict, kind: str = "json") -> Dict:
    if kind == "discord":
        body = json.dumps(build_discord_webhook_payload(payload)).encode("utf-8")
    else:
        body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response_body = response.read()
    return {
        "status": getattr(response, "status", None),
        "body": response_body.decode("utf-8", errors="replace")[:500],
    }


def build_pending_payload(
    host: str,
    lane_ports: Dict[str, int],
    include_local_stats: bool,
    error: Optional[str],
    startup_config: Optional[Dict[str, Any]] = None,
) -> Dict:
    payload = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": host,
        "lane_ports": lane_ports,
        "live": {
            "status": "warming",
            "source": "query",
            "source_lane": None,
            "players_current": None,
            "players_max": None,
            "players_confidence": "low",
            "server_name": None,
            "server_version": None,
            "latency_ms": None,
        },
        "lanes": [],
        "error": error or "cache not ready",
    }
    if include_local_stats:
        payload["local_stats"] = {
            "scope": "api_host",
            "cpu_percent": None,
            "memory_percent": None,
            "memory_used_mb": None,
            "memory_total_mb": None,
            "loadavg_1m": None,
            "loadavg_5m": None,
            "loadavg_15m": None,
            "error": "local stats warming",
        }
    if startup_config is not None:
        payload["startup_config"] = startup_config
    return payload


class Handler(BaseHTTPRequestHandler):
    server_version = USER_AGENT
    sys_version = ""
    config = {}
    cache_lock = threading.Lock()
    cached_payload = None
    cached_at = 0.0
    cache_error = None
    webhook_state = {}
    local_stats_sampler = LocalStatsSampler()
    startup_config = None

    def _send_json(self, status: int, payload: Dict) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self._write_response(status, "application/json", body)

    def _send_html_bytes(self, status: int, payload: bytes) -> None:
        self._write_response(status, "text/html; charset=utf-8", payload)

    def _write_response(self, status: int, content_type: str, payload: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            return

    @classmethod
    def _sample_local_stats(cls) -> Optional[Dict]:
        webhook_cfg = cls.config.get("webhook", {})
        should_sample = cls.config.get("expose_local_stats", False) or any(
            webhook_cfg.get(key) is not None
            for key in ("high_memory_percent", "high_cpu_percent")
        )
        if not should_sample:
            return None
        return cls.local_stats_sampler.sample()

    @classmethod
    def _log_event(cls, event: Dict) -> None:
        print(json.dumps({"event_log": event}, sort_keys=True), flush=True)

    @classmethod
    def _dispatch_webhook_events(cls, payload: Dict) -> None:
        webhook_cfg = cls.config.get("webhook", {})
        if not webhook_cfg.get("url") and not webhook_cfg.get("discord_url") and not cls.config.get("log_events", False):
            return

        events, next_state = evaluate_webhook_events(cls.webhook_state, payload, webhook_cfg)
        cls.webhook_state = next_state
        for event in events:
            if cls.config.get("log_events", False):
                cls._log_event(event)
            # Log every outbound webhook event we trigger (only specified/enabled events reach here).
            targets = []
            if webhook_cfg.get("url"):
                targets.append("webhook")
            if webhook_cfg.get("discord_url"):
                targets.append("discord")
            if targets:
                log_stderr(
                    "webhook event triggered",
                    event=event.get("event"),
                    host=event.get("host"),
                    event_ts=event.get("ts"),
                    targets=targets,
                )
            if webhook_cfg.get("url"):
                threading.Thread(
                    target=cls._post_webhook_target,
                    args=(event, webhook_cfg["url"], "json", webhook_cfg["timeout"]),
                    daemon=True,
                ).start()
            if webhook_cfg.get("discord_url"):
                threading.Thread(
                    target=cls._post_webhook_target,
                    args=(event, webhook_cfg["discord_url"], "discord", webhook_cfg["timeout"]),
                    daemon=True,
                ).start()

    @classmethod
    def _post_webhook_target(cls, event: Dict, target_url: str, target_kind: str, timeout: float) -> None:
        log_stderr(
            "webhook dispatch start",
            event=event.get("event"),
            webhook_url=redact_webhook_url(target_url),
            target_kind=target_kind,
            host=event.get("host"),
            event_ts=event.get("ts"),
        )
        try:
            result = post_webhook(target_url, timeout, event, kind=target_kind)
            log_stderr(
                "webhook dispatch ok",
                event=event.get("event"),
                webhook_url=redact_webhook_url(target_url),
                target_kind=target_kind,
                status=result.get("status"),
                body=result.get("body"),
            )
        except urllib.error.HTTPError as exc:
            log_stderr(
                "webhook dispatch failed",
                event=event.get("event"),
                webhook_url=redact_webhook_url(target_url),
                target_kind=target_kind,
                status=exc.code,
                body=exc.read().decode("utf-8", errors="replace")[:500],
                error=str(exc),
            )
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            log_stderr(
                "webhook dispatch failed",
                event=event.get("event"),
                webhook_url=redact_webhook_url(target_url),
                target_kind=target_kind,
                error=str(exc),
            )

    @classmethod
    def refresh_cache(cls) -> Dict:
        cfg = cls.config
        local_stats = cls._sample_local_stats()
        payload = build_stats_response(
            host=cfg["host"],
            timeout=cfg["timeout"],
            retries=cfg["retries"],
            lane_ports=cfg["lane_ports"],
            local_stats=local_stats if cfg.get("expose_local_stats", False) else None,
            startup_config=cls.startup_config,
        )
        with cls.cache_lock:
            cls.cached_payload = payload
            cls.cached_at = time.time()
            cls.cache_error = None

        if local_stats is not None and "local_stats" not in payload:
            event_payload = dict(payload)
            event_payload["local_stats"] = local_stats
        else:
            event_payload = payload
        cls._dispatch_webhook_events(event_payload)
        return payload

    @classmethod
    def refresh_loop(cls) -> None:
        interval = max(float(cls.config.get("cache_ttl", 3.0)), 0.25)
        while True:
            try:
                cls.refresh_cache()
            except Exception as exc:
                with cls.cache_lock:
                    cls.cache_error = str(exc)
            time.sleep(interval)

    def _get_cached_stats(self) -> Dict:
        cls = type(self)
        with cls.cache_lock:
            if cls.cached_payload is not None:
                return cls.cached_payload
            error = cls.cache_error

        return build_pending_payload(
            host=self.config["host"],
            lane_ports=self.config["lane_ports"],
            include_local_stats=self.config.get("expose_local_stats", False),
            error=error,
            startup_config=self.startup_config,
        )

    def do_GET(self):
        if self.path == "/":
            if not INDEX_HTML_PATH.exists():
                self._send_json(500, {"error": "index.html not found"})
                return
            self._send_html_bytes(200, INDEX_HTML_PATH.read_bytes())
            return

        if self.path == "/healthz":
            self._send_json(200, {"ok": True})
            return

        if self.path == "/v1/stats":
            payload = self._get_cached_stats()
            self._send_json(200, payload)
            return

        self._send_json(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        return

    def version_string(self) -> str:
        return USER_AGENT


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal Enshrouded stats API with optional webhooks.")
    parser.add_argument("--bind", default=os.getenv("ENSHROUDED_API_BIND", "127.0.0.1"), help="Bind address")
    parser.add_argument("--port", type=int, default=int(os.getenv("ENSHROUDED_API_PORT", "8091")), help="HTTP listen port")
    parser.add_argument("--host", default=os.getenv("ENSHROUDED_API_HOST", "127.0.0.1"), help="Target node host for query probes")
    parser.add_argument("--timeout", type=float, default=float(os.getenv("ENSHROUDED_API_TIMEOUT", "1.0")), help="UDP timeout")
    parser.add_argument("--retries", type=int, default=int(os.getenv("ENSHROUDED_API_RETRIES", "2")), help="UDP retries")
    parser.add_argument("--cache-ttl", type=float, default=float(os.getenv("ENSHROUDED_API_CACHE_TTL", "3.0")), help="Stats cache TTL seconds")
    parser.add_argument("--game-port-1", type=int, default=int(os.getenv("ENSHROUDED_API_GAME_PORT_1", str(LANE_DEFAULTS["game_port_1"]))))
    parser.add_argument("--game-port-2", type=int, default=int(os.getenv("ENSHROUDED_API_GAME_PORT_2", str(LANE_DEFAULTS["game_port_2"]))))
    parser.add_argument("--steam-query-port", type=int, default=int(os.getenv("ENSHROUDED_API_STEAM_QUERY_PORT", str(LANE_DEFAULTS["steam_query"]))))
    parser.add_argument("--expose-local-stats", action=argparse.BooleanOptionalAction, default=env_flag("ENSHROUDED_API_EXPOSE_LOCAL_STATS", False), help="Expose local API-host CPU/memory stats in /v1/stats and the UI")
    parser.add_argument("--webhook-url", default=os.getenv("ENSHROUDED_API_WEBHOOK_URL"), help="Optional webhook URL for event posts")
    parser.add_argument("--discord-webhook-url", default=os.getenv("ENSHROUDED_API_DISCORD_WEBHOOK_URL"), help="Optional Discord incoming webhook URL for direct event delivery")
    parser.add_argument("--webhook-timeout", type=float, default=float(os.getenv("ENSHROUDED_API_WEBHOOK_TIMEOUT", "3.0")), help="Webhook POST timeout seconds")
    parser.add_argument("--webhook-events", default=os.getenv("ENSHROUDED_API_WEBHOOK_EVENTS"), help="Comma-separated events: up,down,player_add,player_remove,high_latency,high_memory,high_cpu")
    parser.add_argument("--webhook-high-latency-ms", type=float, help="Trigger high_latency when live latency is at or above this value")
    parser.add_argument("--webhook-high-memory-percent", type=float, help="Trigger high_memory when local API-host memory percent is at or above this value")
    parser.add_argument("--webhook-high-cpu-percent", type=float, help="Trigger high_cpu when local API-host CPU percent is at or above this value")
    parser.add_argument("--log-events", action=argparse.BooleanOptionalAction, default=env_flag("ENSHROUDED_API_LOG_EVENTS", False), help="Log generated event payloads to stdout even when no webhook URL is configured")
    args = parser.parse_args()
    try:
        webhook_events = parse_webhook_events(args.webhook_events)
    except ValueError as exc:
        parser.error(str(exc))
    webhook_high_latency_ms = resolve_optional_float(parser, args.webhook_high_latency_ms, "ENSHROUDED_API_WEBHOOK_HIGH_LATENCY_MS")
    webhook_high_memory_percent = resolve_optional_float(parser, args.webhook_high_memory_percent, "ENSHROUDED_API_WEBHOOK_HIGH_MEMORY_PERCENT")
    webhook_high_cpu_percent = resolve_optional_float(parser, args.webhook_high_cpu_percent, "ENSHROUDED_API_WEBHOOK_HIGH_CPU_PERCENT")

    Handler.config = {
        "bind": args.bind,
        "port": args.port,
        "host": args.host,
        "timeout": args.timeout,
        "retries": args.retries,
        "cache_ttl": args.cache_ttl,
        "expose_local_stats": args.expose_local_stats,
        "log_events": args.log_events,
        "server_config_path": str(DEFAULT_SERVER_CONFIG_PATH),
        "lane_ports": {
            "game_port_1": args.game_port_1,
            "game_port_2": args.game_port_2,
            "steam_query": args.steam_query_port,
        },
        "webhook": {
            "url": args.webhook_url,
            "discord_url": args.discord_webhook_url,
            "timeout": args.webhook_timeout,
            "events": webhook_events,
            "high_latency_ms": webhook_high_latency_ms,
            "high_memory_percent": webhook_high_memory_percent,
            "high_cpu_percent": webhook_high_cpu_percent,
        },
    }
    Handler.webhook_state = {}
    Handler.cached_payload = None
    Handler.cached_at = 0.0
    Handler.cache_error = None
    Handler.startup_config = build_startup_config(Handler.config)
    log_stderr("startup config", startup_config=Handler.startup_config)

    try:
        Handler.refresh_cache()
    except Exception as exc:
        with Handler.cache_lock:
            Handler.cache_error = str(exc)
    threading.Thread(target=Handler.refresh_loop, daemon=True).start()

    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    log_stderr(f"listening on http://{args.bind}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
