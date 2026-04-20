import datetime

from app.classes.shared.stats_helpers import StatsConverter


def test_prepare_chart_datasets_includes_tps_series():
    now = datetime.datetime.now()
    stats = [
        {
            "created": now,
            "online": 3,
            "mem_percent": 25.0,
            "mem": 1024 * 1024 * 1024,
            "cpu": 11.5,
            "telemetry_tps": 19.95,
        },
        {
            "created": now + datetime.timedelta(minutes=1),
            "online": None,
            "mem_percent": None,
            "mem": None,
            "cpu": None,
            "telemetry_tps": None,
        },
    ]

    chart = StatsConverter.prepare_chart_datasets(stats, server_type="minecraft-java")
    assert chart["tps"] == [19.95, None]
