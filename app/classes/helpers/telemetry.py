from __future__ import annotations

import ipaddress
import typing as t


def normalize_telemetry_port(raw_value: t.Any) -> int:
    """Normalize telemetry port to a safe integer.

    Empty/invalid values are treated as disabled (0).
    """
    if raw_value is None:
        return 0

    if isinstance(raw_value, bool):
        return 0

    if isinstance(raw_value, str):
        raw_value = raw_value.strip()
        if raw_value == "":
            return 0

    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return 0

    if value < 1 or value > 65535:
        return 0
    return value


def build_telemetry_url(host: str, port: int) -> str:
    """Build telemetry endpoint URL for the host/port pair."""
    safe_host = (host or "").strip()
    if safe_host in ("", "0.0.0.0", "::", "[::]"):
        safe_host = "127.0.0.1"

    try:
        ip_obj = ipaddress.ip_address(safe_host)
        if ip_obj.version == 6:
            safe_host = f"[{safe_host}]"
    except ValueError:
        # Hostname or other non-IP string; keep as-is.
        pass

    return f"http://{safe_host}:{port}/telemetry"


def parse_telemetry_payload(payload: t.Any) -> dict:
    """Parse telemetry payload into Crafty-friendly fields."""
    result = {
        "telemetry_tps": False,
        "telemetry_mspt": False,
        "telemetry_players": [],
    }
    if not isinstance(payload, dict):
        return result

    tps = payload.get("tps")
    mspt = payload.get("mspt")
    players = payload.get("players")

    if isinstance(tps, (int, float)) and not isinstance(tps, bool):
        result["telemetry_tps"] = float(tps)
    if isinstance(mspt, (int, float)) and not isinstance(mspt, bool):
        result["telemetry_mspt"] = float(mspt)

    if isinstance(players, list):
        names = []
        for player in players:
            if isinstance(player, dict):
                name = player.get("name")
                if isinstance(name, str) and name.strip():
                    names.append(name)
            elif isinstance(player, str) and player.strip():
                names.append(player)
        result["telemetry_players"] = names

    return result
