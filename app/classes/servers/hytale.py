"""Hytale-specific player-management helpers."""

import datetime
import json
import logging
from pathlib import Path

from app.classes.helpers.helpers import Helpers

logger = logging.getLogger(__name__)


def resolve_player_name(server_path: str, player_uuid: str) -> str:
    if not player_uuid:
        return player_uuid
    profile_path = Path(server_path, "universe", "players", f"{player_uuid}.json")
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return player_uuid
    components = profile.get("Components", {})
    return (
        components.get("Nameplate", {}).get("Text")
        or components.get("DisplayName", {}).get("DisplayName", {}).get("RawText")
        or player_uuid
    )


def get_banned_players(server_path: str) -> list[dict]:
    """Read Hytale bans.json and normalise it for the player table."""
    bans_path = Path(server_path, "bans.json")
    try:
        bans = json.loads(
            Path(Helpers.get_os_understandable_path(str(bans_path))).read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Unable to read Hytale bans file %s: %s", bans_path, exc)
        return []
    if not isinstance(bans, list):
        return []

    entries = []
    for ban in bans:
        if not isinstance(ban, dict):
            continue
        target = str(ban.get("target", ""))
        source = str(ban.get("by", ""))
        if not source.strip("0-"):
            source = "Server"
        try:
            created = datetime.datetime.fromtimestamp(
                float(ban.get("timestamp", 0)) / 1000,
                tz=datetime.timezone.utc,
            ).strftime("%Y-%m-%d %H:%M:%S %z")
        except (TypeError, ValueError, OSError):
            created = "Unknown"
        entries.append(
            {
                "uuid": target,
                "name": resolve_player_name(server_path, target),
                "source": source,
                "reason": str(ban.get("reason", "None")),
                "created": created,
            }
        )
    return entries
