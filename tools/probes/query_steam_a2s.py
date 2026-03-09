#!/usr/bin/env python3
import argparse
import json
import socket
import struct
import time
from typing import Any, Dict, List, Optional, Tuple

A2S_PREFIX = b"\xff\xff\xff\xff"
A2S_INFO_REQUEST = A2S_PREFIX + b"TSource Engine Query\x00"
A2S_QUERY_TYPES = ("info", "player", "rules")
A2S_REQUEST_HEADERS = {
    "player": 0x55,
    "rules": 0x56,
}
A2S_RESPONSE_HEADERS = {
    "info": 0x49,
    "player": 0x44,
    "rules": 0x45,
}


class A2SDecodeError(RuntimeError):
    pass


def _read_cstring(data: bytes, offset: int) -> Tuple[str, int]:
    end = data.find(b"\x00", offset)
    if end == -1:
        raise A2SDecodeError("unterminated cstring")
    value = data[offset:end].decode("utf-8", errors="replace")
    return value, end + 1


def _require(data: bytes, offset: int, length: int) -> None:
    if offset + length > len(data):
        raise A2SDecodeError("truncated packet")


def _packet_header(packet: bytes, expected: int) -> int:
    if len(packet) < 6:
        raise A2SDecodeError("packet too short")
    if not packet.startswith(A2S_PREFIX):
        raise A2SDecodeError("invalid packet prefix")

    header = packet[4]
    if header != expected:
        raise A2SDecodeError(f"unexpected packet header 0x{header:02x}")
    return header


def decode_a2s_info_packet(packet: bytes) -> Dict[str, Any]:
    _packet_header(packet, A2S_RESPONSE_HEADERS["info"])

    offset = 5
    _require(packet, offset, 1)
    protocol = packet[offset]
    offset += 1

    name, offset = _read_cstring(packet, offset)
    map_name, offset = _read_cstring(packet, offset)
    folder, offset = _read_cstring(packet, offset)
    game, offset = _read_cstring(packet, offset)

    _require(packet, offset, 2 + 6)
    app_id = struct.unpack_from("<H", packet, offset)[0]
    offset += 2

    players = packet[offset]
    max_players = packet[offset + 1]
    bots = packet[offset + 2]
    server_type = chr(packet[offset + 3])
    environment = chr(packet[offset + 4])
    visibility = packet[offset + 5]
    offset += 6

    _require(packet, offset, 1)
    vac = packet[offset]
    offset += 1

    version, offset = _read_cstring(packet, offset)

    extras = {}
    if offset < len(packet):
        edf = packet[offset]
        offset += 1
        extras["edf"] = edf

        if edf & 0x80:
            _require(packet, offset, 2)
            extras["port"] = struct.unpack_from("<H", packet, offset)[0]
            offset += 2
        if edf & 0x10:
            _require(packet, offset, 8)
            extras["steam_id"] = struct.unpack_from("<Q", packet, offset)[0]
            offset += 8
        if edf & 0x40:
            _require(packet, offset, 2)
            spectator_port = struct.unpack_from("<H", packet, offset)[0]
            offset += 2
            spectator_name, offset = _read_cstring(packet, offset)
            extras["spectator_port"] = spectator_port
            extras["spectator_name"] = spectator_name
        if edf & 0x20:
            keywords, offset = _read_cstring(packet, offset)
            extras["keywords"] = keywords
        if edf & 0x01:
            _require(packet, offset, 8)
            extras["game_id"] = struct.unpack_from("<Q", packet, offset)[0]
            offset += 8

    return {
        "protocol": protocol,
        "name": name,
        "map": map_name,
        "folder": folder,
        "game": game,
        "app_id": app_id,
        "players": players,
        "max_players": max_players,
        "bots": bots,
        "server_type": server_type,
        "environment": environment,
        "visibility": visibility,
        "vac": vac,
        "version": version,
        "extras": extras,
    }


def decode_a2s_player_packet(packet: bytes) -> Dict[str, Any]:
    _packet_header(packet, A2S_RESPONSE_HEADERS["player"])

    offset = 5
    _require(packet, offset, 1)
    player_count = packet[offset]
    offset += 1

    players: List[Dict[str, Any]] = []
    for _ in range(player_count):
        _require(packet, offset, 1)
        index = packet[offset]
        offset += 1
        name, offset = _read_cstring(packet, offset)
        _require(packet, offset, 8)
        score = struct.unpack_from("<i", packet, offset)[0]
        offset += 4
        duration_seconds = round(struct.unpack_from("<f", packet, offset)[0], 2)
        offset += 4
        players.append(
            {
                "index": index,
                "name": name,
                "score": score,
                "duration_seconds": duration_seconds,
            }
        )

    return {
        "player_count": player_count,
        "players": players,
    }


def decode_a2s_rules_packet(packet: bytes) -> Dict[str, Any]:
    _packet_header(packet, A2S_RESPONSE_HEADERS["rules"])

    offset = 5
    _require(packet, offset, 2)
    rule_count = struct.unpack_from("<H", packet, offset)[0]
    offset += 2

    rules: List[Dict[str, str]] = []
    for _ in range(rule_count):
        name, offset = _read_cstring(packet, offset)
        value, offset = _read_cstring(packet, offset)
        rules.append({"name": name, "value": value})

    return {
        "rule_count": rule_count,
        "rules": rules,
    }


def _parse_challenge(packet: bytes) -> Optional[int]:
    if len(packet) >= 9 and packet.startswith(A2S_PREFIX) and packet[4] == 0x41:
        return struct.unpack_from("<i", packet, 5)[0]
    return None


def _split_packet_payload_offset(packet: bytes) -> int:
    if len(packet) >= 14 and packet[10:14] == A2S_PREFIX:
        return 10
    if len(packet) >= 16 and packet[12:16] == A2S_PREFIX:
        return 12
    if len(packet) >= 12:
        return 12
    raise A2SDecodeError("truncated split packet")


def _decode_split_packet(packet: bytes) -> Dict[str, Any]:
    if len(packet) < 10:
        raise A2SDecodeError("packet too short")
    if struct.unpack_from("<i", packet, 0)[0] != -2:
        raise A2SDecodeError("not a split packet")

    response_id_raw = struct.unpack_from("<I", packet, 4)[0]
    compressed = bool(response_id_raw & 0x80000000)
    if compressed:
        raise A2SDecodeError("compressed split packets are not supported")

    payload_offset = _split_packet_payload_offset(packet)
    total = packet[8]
    number = packet[9]
    if total == 0:
        raise A2SDecodeError("invalid split packet total")
    if number >= total:
        raise A2SDecodeError("invalid split packet index")
    return {
        "response_id": response_id_raw,
        "total": total,
        "number": number,
        "payload": packet[payload_offset:],
    }


def _recv_packet(sock: socket.socket) -> Tuple[bytes, Tuple[str, int]]:
    return sock.recvfrom(8192)


def _recv_reassembled_packet(sock: socket.socket, first_packet: bytes, first_addr: Tuple[str, int]) -> Tuple[bytes, Tuple[str, int]]:
    if len(first_packet) < 4 or struct.unpack_from("<i", first_packet, 0)[0] != -2:
        return first_packet, first_addr

    first_part = _decode_split_packet(first_packet)
    total = first_part["total"]
    parts = {first_part["number"]: first_part["payload"]}

    while len(parts) < total:
        packet, addr = _recv_packet(sock)
        part = _decode_split_packet(packet)
        if part["response_id"] != first_part["response_id"]:
            continue
        parts[part["number"]] = part["payload"]
        first_addr = addr

    assembled = b"".join(parts[index] for index in range(total))
    return assembled, first_addr


def _build_request(query_type: str, challenge: Optional[int] = None) -> bytes:
    if query_type == "info":
        if challenge is None:
            return A2S_INFO_REQUEST
        return A2S_INFO_REQUEST + struct.pack("<i", challenge)

    if query_type not in A2S_REQUEST_HEADERS:
        raise ValueError(f"unsupported query_type: {query_type}")

    challenge_value = -1 if challenge is None else challenge
    return A2S_PREFIX + bytes([A2S_REQUEST_HEADERS[query_type]]) + struct.pack("<i", challenge_value)


def _exchange(sock: socket.socket, host: str, port: int, request: bytes) -> Tuple[bytes, Tuple[str, int], float]:
    started_at = time.monotonic()
    sock.sendto(request, (host, port))
    packet, addr = _recv_packet(sock)
    packet, addr = _recv_reassembled_packet(sock, packet, addr)
    latency_ms = round((time.monotonic() - started_at) * 1000.0, 2)
    return packet, addr, latency_ms


def _query_a2s(query_type: str, host: str, port: int, timeout: float = 1.5, retries: int = 2) -> Dict[str, Any]:
    last_error = "unknown error"
    decoder = {
        "info": decode_a2s_info_packet,
        "player": decode_a2s_player_packet,
        "rules": decode_a2s_rules_packet,
    }[query_type]

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        for attempts in range(1, retries + 1):
            try:
                packet, addr, latency_ms = _exchange(sock, host, port, _build_request(query_type))
                challenge = _parse_challenge(packet)
                if challenge is not None:
                    packet, addr, latency_ms = _exchange(sock, host, port, _build_request(query_type, challenge))

                decoded = decoder(packet)
                return {
                    "ok": True,
                    "source": "query",
                    "host": host,
                    "port": port,
                    "remote": f"{addr[0]}:{addr[1]}",
                    "latency_ms": latency_ms,
                    "attempts": attempts,
                    "a2s": decoded,
                }
            except (socket.timeout, OSError, A2SDecodeError, ValueError, struct.error) as exc:
                last_error = str(exc)

    return {
        "ok": False,
        "source": "query",
        "host": host,
        "port": port,
        "attempts": retries,
        "error": last_error,
    }


def query_a2s_info(host: str, port: int, timeout: float = 1.5, retries: int = 2) -> Dict[str, Any]:
    return _query_a2s("info", host=host, port=port, timeout=timeout, retries=retries)


def query_a2s_player(host: str, port: int, timeout: float = 1.5, retries: int = 2) -> Dict[str, Any]:
    return _query_a2s("player", host=host, port=port, timeout=timeout, retries=retries)


def query_a2s_rules(host: str, port: int, timeout: float = 1.5, retries: int = 2) -> Dict[str, Any]:
    return _query_a2s("rules", host=host, port=port, timeout=timeout, retries=retries)


def query_a2s_bundle(host: str, port: int, timeout: float = 1.5, retries: int = 2) -> Dict[str, Dict[str, Any]]:
    return {
        "info": query_a2s_info(host=host, port=port, timeout=timeout, retries=retries),
        "player": query_a2s_player(host=host, port=port, timeout=timeout, retries=retries),
        "rules": query_a2s_rules(host=host, port=port, timeout=timeout, retries=retries),
    }


def decode_hex_file(path: str, query_type: str = "info") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        raw = handle.read()
    hex_data = "".join(ch for ch in raw if ch not in " \n\t\r")
    packet = bytes.fromhex(hex_data)
    decoder = {
        "info": decode_a2s_info_packet,
        "player": decode_a2s_player_packet,
        "rules": decode_a2s_rules_packet,
    }[query_type]
    return {
        "ok": True,
        "source": "fixture",
        "a2s": decoder(packet),
    }


def summarize_info(result: Dict[str, Any]) -> Dict[str, Any]:
    if not result.get("ok"):
        return {
            "ok": False,
            "error": result.get("error"),
        }

    a2s = result["a2s"]
    return {
        "ok": True,
        "latency_ms": result.get("latency_ms"),
        "server_name": a2s.get("name"),
        "game": a2s.get("game"),
        "players_current": a2s.get("players"),
        "players_max": a2s.get("max_players"),
        "version": a2s.get("version"),
        "query_port_reported": a2s.get("extras", {}).get("port"),
    }


def summarize_player(result: Dict[str, Any]) -> Dict[str, Any]:
    if not result.get("ok"):
        return {
            "ok": False,
            "error": result.get("error"),
        }

    a2s = result["a2s"]
    players = a2s.get("players", [])
    return {
        "ok": True,
        "latency_ms": result.get("latency_ms"),
        "player_count": a2s.get("player_count"),
        "players": players,
    }


def summarize_rules(result: Dict[str, Any]) -> Dict[str, Any]:
    if not result.get("ok"):
        return {
            "ok": False,
            "error": result.get("error"),
        }

    a2s = result["a2s"]
    rules = a2s.get("rules", [])
    return {
        "ok": True,
        "latency_ms": result.get("latency_ms"),
        "rule_count": a2s.get("rule_count"),
        "rules": rules,
    }


def summarize_bundle(bundle: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {
        "info": summarize_info(bundle["info"]),
        "player": summarize_player(bundle["player"]),
        "rules": summarize_rules(bundle["rules"]),
    }


def flatten_result(result: Dict[str, Any]) -> Dict[str, Any]:
    if not result.get("ok"):
        return dict(result)

    flattened = dict(result)
    decoded = flattened.pop("a2s", None)
    if isinstance(decoded, dict):
        flattened.update(decoded)
    return flattened


def summarize(result: Dict[str, Any]) -> Dict[str, Any]:
    a2s = result.get("a2s") or {}
    if "player_count" in a2s:
        return summarize_player(result)
    if "rule_count" in a2s:
        return summarize_rules(result)
    return summarize_info(result)


def _print_result(result: Dict[str, Any], summary: bool) -> None:
    if "info" in result and "player" in result and "rules" in result:
        if summary:
            payload = {"a2s": summarize_bundle(result)}
        else:
            payload = {"a2s": {name: flatten_result(item) for name, item in result.items()}}
    elif summary:
        payload = summarize(result)
    else:
        payload = flatten_result(result)
    print(json.dumps(payload, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Steam A2S probe tool for Enshrouded query ports.")
    parser.add_argument("--host", default="127.0.0.1", help="Query target host")
    parser.add_argument("--port", type=int, default=15637, help="Query target UDP port")
    parser.add_argument("--timeout", type=float, default=1.5, help="UDP socket timeout seconds")
    parser.add_argument("--retries", type=int, default=2, help="Probe retry attempts")
    parser.add_argument("--query-type", choices=(*A2S_QUERY_TYPES, "all"), default="info", help="A2S query type to run")
    parser.add_argument("--decode-hex", help="Decode A2S packet from hex fixture file")
    parser.add_argument("--summary", action="store_true", help="Print compact summary")
    args = parser.parse_args()

    if args.decode_hex and args.query_type == "all":
        parser.error("--decode-hex requires a single --query-type")

    if args.decode_hex:
        result = decode_hex_file(args.decode_hex, query_type=args.query_type)
    elif args.query_type == "all":
        result = query_a2s_bundle(args.host, args.port, timeout=args.timeout, retries=args.retries)
    else:
        result = _query_a2s(args.query_type, args.host, args.port, timeout=args.timeout, retries=args.retries)

    _print_result(result, summary=args.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
