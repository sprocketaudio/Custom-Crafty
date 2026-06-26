import os
from pathlib import Path

from app.classes.web.routes.api.servers.server.logs import ApiServersServerLogsHandler


def build_handler(tmp_path: Path) -> ApiServersServerLogsHandler:
    handler = ApiServersServerLogsHandler.__new__(ApiServersServerLogsHandler)
    handler._server_root_path = lambda _server_data: tmp_path
    handler._resolve_log_source = lambda _server_data, _source: tmp_path / "logs" / "latest.log"
    return handler


def test_list_available_logs_includes_logs_and_crash_reports(tmp_path):
    logs_dir = tmp_path / "logs"
    crash_dir = tmp_path / "crash-reports"
    logs_dir.mkdir(parents=True)
    crash_dir.mkdir(parents=True)

    latest_log = logs_dir / "latest.log"
    latest_log.write_text("latest", encoding="utf-8")
    crash_report = crash_dir / "crash-2026-06-26.log"
    crash_report.write_text("crash", encoding="utf-8")
    latest_stat = latest_log.stat()
    os.utime(
        crash_report,
        (latest_stat.st_atime + 5, latest_stat.st_mtime + 5),
    )

    handler = build_handler(tmp_path)

    sources = handler._list_available_logs({"path": str(tmp_path), "log_path": "./logs/latest.log"})

    assert [entry["path"] for entry in sources] == [
        "crash-reports/crash-2026-06-26.log",
        "logs/latest.log",
    ]


def test_list_available_logs_skips_unreadable_entries(tmp_path, monkeypatch):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True)
    latest_log = logs_dir / "latest.log"
    latest_log.write_text("latest", encoding="utf-8")
    unreadable_dir = logs_dir / "secret"
    unreadable_dir.mkdir()
    unreadable_log = unreadable_dir / "hidden.log"
    unreadable_log.write_text("hidden", encoding="utf-8")

    original_stat = Path.stat

    def fake_stat(path_obj: Path, *args, **kwargs):
        if path_obj == unreadable_dir or path_obj == unreadable_log:
            raise PermissionError("permission denied")
        return original_stat(path_obj, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fake_stat)

    handler = build_handler(tmp_path)

    sources = handler._list_available_logs({"path": str(tmp_path), "log_path": "./logs/latest.log"})

    assert [entry["path"] for entry in sources] == ["logs/latest.log"]
