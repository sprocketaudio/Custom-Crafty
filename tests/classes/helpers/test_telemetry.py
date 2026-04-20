import pytest

from app.classes.helpers.telemetry import (
    build_telemetry_url,
    normalize_telemetry_port,
    parse_telemetry_payload,
)


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (None, 0),
        ("", 0),
        ("  ", 0),
        (0, 0),
        ("0", 0),
        (1, 1),
        ("25565", 25565),
        (65535, 65535),
        ("65536", 0),
        ("-1", 0),
        ("abc", 0),
        (False, 0),
        (True, 0),
    ],
)
def test_normalize_telemetry_port(raw_value, expected):
    assert normalize_telemetry_port(raw_value) == expected


@pytest.mark.parametrize(
    ("host", "port", "expected"),
    [
        ("127.0.0.1", 9123, "http://127.0.0.1:9123/telemetry"),
        ("0.0.0.0", 9123, "http://127.0.0.1:9123/telemetry"),
        ("example.local", 9123, "http://example.local:9123/telemetry"),
        ("::1", 9123, "http://[::1]:9123/telemetry"),
    ],
)
def test_build_telemetry_url(host, port, expected):
    assert build_telemetry_url(host, port) == expected


def test_parse_telemetry_payload_valid():
    parsed = parse_telemetry_payload(
        {
            "mc": "1.21.1",
            "loader": "neoforge",
            "mspt": 18.4,
            "tps": 20.0,
            "players": [{"name": "Alice", "uuid": "u1"}, {"name": "Bob", "uuid": "u2"}],
        }
    )
    assert parsed["telemetry_tps"] == 20.0
    assert parsed["telemetry_mspt"] == 18.4
    assert parsed["telemetry_players"] == ["Alice", "Bob"]


def test_parse_telemetry_payload_invalid_shape():
    parsed = parse_telemetry_payload({"tps": "20", "mspt": None, "players": [1, {"x": 1}]})
    assert parsed["telemetry_tps"] is False
    assert parsed["telemetry_mspt"] is False
    assert parsed["telemetry_players"] == []
