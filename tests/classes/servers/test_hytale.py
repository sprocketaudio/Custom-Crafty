import json

from app.classes.servers.hytale import get_banned_players


def test_hytale_bans_are_normalised_for_player_management(tmp_path):
    player_id = "123e4567-e89b-12d3-a456-426614174000"
    profile_dir = tmp_path / "universe" / "players"
    profile_dir.mkdir(parents=True)
    (profile_dir / f"{player_id}.json").write_text(
        json.dumps({"Components": {"Nameplate": {"Text": "Aero"}}}),
        encoding="utf-8",
    )
    (tmp_path / "bans.json").write_text(
        json.dumps(
            [
                {
                    "target": player_id,
                    "by": "00000000-0000-0000-0000-000000000000",
                    "reason": "Test ban",
                    "timestamp": 1_700_000_000_000,
                }
            ]
        ),
        encoding="utf-8",
    )

    assert get_banned_players(str(tmp_path)) == [
        {
            "uuid": player_id,
            "name": "Aero",
            "source": "Server",
            "reason": "Test ban",
            "created": "2023-11-14 22:13:20 +0000",
        }
    ]
