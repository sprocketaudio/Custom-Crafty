from app.classes.shared.server import ServerInstance
from app.classes.web.panel_handler import PanelHandler


def test_cached_players_sort_online_first_then_most_recently_seen():
    players = [
        {"name": "OldOffline", "status": "Offline", "last_seen": "01/01/2025 10:00"},
        {"name": "OlderOnline", "status": "Online", "last_seen": "02/01/2025 10:00"},
        {"name": "RecentOffline", "status": "Offline", "last_seen": "03/01/2025 10:00"},
        {"name": "RecentOnline", "status": "Online", "last_seen": "04/01/2025 10:00"},
    ]

    sorted_players = PanelHandler._sort_cached_players(players)

    assert [player["name"] for player in sorted_players] == [
        "RecentOnline",
        "OlderOnline",
        "RecentOffline",
        "OldOffline",
    ]


def test_player_cache_preserves_online_join_time_and_updates_disconnect_time():
    instance = ServerInstance.__new__(ServerInstance)
    instance.player_cache = [
        {"name": "StillOnline", "status": "Online", "last_seen": "01/01/2025 10:00"},
        {"name": "Left", "status": "Online", "last_seen": "01/01/2025 11:00"},
    ]
    instance.check_running = lambda: True
    instance.get_formatted_server_players = lambda: ["StillOnline", "Joined"]

    instance.cache_players()

    by_name = {player["name"]: player for player in instance.player_cache}
    assert by_name["StillOnline"] == {
        "name": "StillOnline",
        "status": "Online",
        "last_seen": "01/01/2025 10:00",
    }
    assert by_name["Left"]["status"] == "Offline"
    assert by_name["Joined"]["status"] == "Online"
