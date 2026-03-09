#!/usr/bin/env python3
import argparse
import importlib.util
import struct
from pathlib import Path


def load_module(probe_path: Path):
    spec = importlib.util.spec_from_file_location("query_steam_a2s", probe_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeSocket:
    def __init__(self, responses):
        self.responses = list(responses)
        self.sent = []
        self.timeout = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def settimeout(self, timeout):
        self.timeout = timeout

    def sendto(self, payload, addr):
        self.sent.append((payload, addr))

    def recvfrom(self, size):
        if not self.responses:
            raise AssertionError("unexpected recvfrom with no remaining responses")
        return self.responses.pop(0)


def build_split_packets(payload: bytes, response_id: int = 1234):
    midpoint = len(payload) // 2
    first = payload[:midpoint]
    second = payload[midpoint:]
    header_1 = struct.pack("<iIBB", -2, response_id, 2, 0) + struct.pack("<H", len(payload))
    header_2 = struct.pack("<iIBB", -2, response_id, 2, 1) + struct.pack("<H", len(payload))
    return header_1 + first, header_2 + second


def build_invalid_split_packet(payload: bytes, response_id: int = 1234):
    return struct.pack("<iIBB", -2, response_id, 2, 5) + struct.pack("<H", len(payload)) + payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root_dir")
    args = parser.parse_args()

    root_dir = Path(args.root_dir)
    probe_path = root_dir / "probes" / "query_steam_a2s.py"
    module = load_module(probe_path)

    player_response = bytes.fromhex(
        (root_dir / "fixtures" / "query" / "a2s-player-response.hex").read_text(encoding="utf-8").strip()
    )
    rules_response = bytes.fromhex(
        (root_dir / "fixtures" / "query" / "a2s-rules-response.hex").read_text(encoding="utf-8").strip()
    )
    split_rules_1, split_rules_2 = build_split_packets(rules_response)

    challenge_value = 24680
    challenge_packet = module.A2S_PREFIX + bytes([0x41]) + struct.pack("<i", challenge_value)

    original_socket = module.socket.socket
    try:
        player_socket = FakeSocket(
            [
                (challenge_packet, ("127.0.0.1", 32015)),
                (player_response, ("127.0.0.1", 32015)),
            ]
        )
        module.socket.socket = lambda *args, **kwargs: player_socket
        player_result = module.query_a2s_player("127.0.0.1", 32015, timeout=1.0, retries=1)
        assert player_result["ok"] is True
        assert player_result["a2s"]["player_count"] == 2
        assert player_socket.sent[0][0] == module._build_request("player")
        assert player_socket.sent[1][0] == module._build_request("player", challenge_value)

        rules_socket = FakeSocket(
            [
                (challenge_packet, ("127.0.0.1", 32015)),
                (split_rules_1, ("127.0.0.1", 32015)),
                (split_rules_2, ("127.0.0.1", 32015)),
            ]
        )
        module.socket.socket = lambda *args, **kwargs: rules_socket
        rules_result = module.query_a2s_rules("127.0.0.1", 32015, timeout=1.0, retries=1)
        assert rules_result["ok"] is True
        assert rules_result["a2s"]["rule_count"] == 3
        assert rules_socket.sent[0][0] == module._build_request("rules")
        assert rules_socket.sent[1][0] == module._build_request("rules", challenge_value)

        packet, addr = module._recv_reassembled_packet(player_socket, b"\x01\x02\x03", ("127.0.0.1", 32015))
        assert packet == b"\x01\x02\x03"
        assert addr == ("127.0.0.1", 32015)

        bad_rules_socket = FakeSocket(
            [
                (challenge_packet, ("127.0.0.1", 32015)),
                (build_invalid_split_packet(rules_response), ("127.0.0.1", 32015)),
            ]
        )
        module.socket.socket = lambda *args, **kwargs: bad_rules_socket
        bad_rules_result = module.query_a2s_rules("127.0.0.1", 32015, timeout=1.0, retries=1)
        assert bad_rules_result["ok"] is False
        assert "invalid split packet index" in bad_rules_result["error"]
    finally:
        module.socket.socket = original_socket

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
