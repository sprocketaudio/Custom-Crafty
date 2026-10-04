import json
import queue
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.classes.shared.server import (
    SERVER_SCHEDULER_JOB_DEFAULTS,
    SERVER_SCHEDULER_MAX_WORKERS,
    ServerInstance,
    _server_scheduler_executors,
)
from app.classes.shared.tasks import SCHEDULE_JOB_DEFAULTS, TasksManager
from app.classes.web.base_handler import BaseHandler
from app.classes.web.websocket_handler import WebSocketHandler
from app.classes.web.routes.api.crafty.config.index import config_json_schema
from app.classes.web.routes.api.crafty.upload.index import IMAGE_MIME_TYPES


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_profile_image_uploads_exclude_active_content_formats():
    assert "image/svg+xml" not in IMAGE_MIME_TYPES
    assert set(IMAGE_MIME_TYPES) == {
        "image/bmp",
        "image/gif",
        "image/jpeg",
        "image/pipeg",
        "image/tiff",
        "image/x-icon",
        "image/png",
        "image/webp",
    }


def test_server_update_check_handles_connection_errors(monkeypatch):
    instance = ServerInstance.__new__(ServerInstance)
    instance.settings = {
        "update_watcher": True,
        "path": "/tmp/server",
        "executable": "server.jar",
    }
    instance.helper = SimpleNamespace(
        crypto_helper=SimpleNamespace(calculate_file_hash_sha256=lambda _path: "local")
    )
    instance.server_object = SimpleNamespace(
        executable_update_url="https://example.com/server.jar"
    )

    def raise_connection_error(*_args, **_kwargs):
        from requests.exceptions import ConnectionError

        raise ConnectionError("offline")

    monkeypatch.setattr("app.classes.shared.server.requests.get", raise_connection_error)

    instance.check_server_version()

    assert instance.update_available is False


def test_reaction_schedule_update_uses_interval_type(monkeypatch):
    manager = TasksManager.__new__(TasksManager)
    normalized = {"interval_type": "reaction", "enabled": False}
    removed = []

    monkeypatch.setattr(
        "app.classes.shared.tasks.HelpersManagement.update_scheduled_task",
        lambda *_args: None,
    )
    manager._normalize_update_job_data = lambda *_args: normalized
    manager._remove_scheduler_job_if_present = lambda *args: removed.append(args)

    manager.update_job(17, {"interval_type": "reaction", "parent": None})

    assert len(removed) == 1


def test_removing_all_server_tasks_removes_reactions_and_pending_jobs(monkeypatch):
    manager = TasksManager.__new__(TasksManager)
    schedules = [
        SimpleNamespace(schedule_id=10, interval_type="minutes"),
        SimpleNamespace(schedule_id=11, interval_type="reaction"),
    ]
    removed_jobs = []
    deleted_servers = []

    monkeypatch.setattr(
        "app.classes.shared.tasks.HelpersManagement.get_schedules_by_server",
        lambda _server_id: schedules,
    )
    monkeypatch.setattr(
        "app.classes.shared.tasks.HelpersManagement.delete_scheduled_task_by_server",
        deleted_servers.append,
    )
    manager._remove_scheduler_job_if_present = removed_jobs.append

    manager.remove_all_server_tasks("server-1")

    assert removed_jobs == [10, 11]
    assert deleted_servers == ["server-1"]


def test_stopping_server_cancels_pending_lifecycle_starts(monkeypatch):
    manager = TasksManager.__new__(TasksManager)
    command_queue = queue.Queue()
    command_queue.put({"server_id": "server-1", "command": "start_server"})
    command_queue.put({"server_id": "server-2", "command": "restart_server"})
    command_queue.put({"server_id": "server-1", "command": "save-all"})
    command_queue.put({"server_id": "server-1", "command": "restart_server"})
    removed_reaction_jobs = []
    manager.controller = SimpleNamespace(
        management=SimpleNamespace(command_queue=command_queue)
    )
    manager._remove_scheduler_job_if_present = lambda schedule_id: (
        removed_reaction_jobs.append(schedule_id) or True
    )
    monkeypatch.setattr(
        "app.classes.shared.tasks.HelpersManagement.get_schedules_by_server",
        lambda _server_id: [
            SimpleNamespace(
                schedule_id=20,
                interval_type="reaction",
                command="restart_server",
                action="restart",
            ),
            SimpleNamespace(
                schedule_id=21,
                interval_type="reaction",
                command="tellraw @a hi",
                action="command",
            ),
        ],
    )

    cancelled = manager.cancel_pending_lifecycle_starts("server-1")

    assert cancelled == 3
    assert list(command_queue.queue) == [
        {"server_id": "server-2", "command": "restart_server"},
        {"server_id": "server-1", "command": "save-all"},
    ]
    assert removed_reaction_jobs == [20]


def test_session_log_has_a_size_ceiling():
    logging_config = json.loads(
        (PROJECT_ROOT / "app" / "config" / "logging.json").read_text(encoding="utf-8")
    )

    assert logging_config["handlers"]["session_file_handler"]["maxBytes"] == 1_073_741_824


def test_run_task_now_queues_only_the_task_owned_by_the_requested_server():
    manager = TasksManager.__new__(TasksManager)
    queued = []
    manager.controller = SimpleNamespace(
        management=SimpleNamespace(
            get_scheduled_task=lambda _schedule_id: {
                "server_id": {"server_id": "server-1"},
                "command": "save-all",
                "action_id": 3,
            },
            queue_command=queued.append,
        )
    )

    manager.run_task_now(7, 12, "server-1")

    assert queued == [
        {"server_id": "server-1", "user_id": 12, "command": "save-all", "action_id": 3}
    ]


def test_run_task_now_rejects_a_schedule_from_another_server():
    manager = TasksManager.__new__(TasksManager)
    manager.controller = SimpleNamespace(
        management=SimpleNamespace(
            get_scheduled_task=lambda _schedule_id: {
                "server_id": "server-1",
                "command": "save-all",
            }
        )
    )

    with pytest.raises(ValueError, match="does not belong"):
        manager.run_task_now(7, 12, "server-2")


def test_server_schedules_do_not_catch_up_after_a_stall():
    assert SCHEDULE_JOB_DEFAULTS == {
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 1,
    }


def test_per_server_maintenance_schedulers_are_bounded():
    assert SERVER_SCHEDULER_JOB_DEFAULTS == SCHEDULE_JOB_DEFAULTS
    executors = _server_scheduler_executors()
    assert SERVER_SCHEDULER_MAX_WORKERS == 2
    assert executors["default"]._pool._max_workers == SERVER_SCHEDULER_MAX_WORKERS


def test_start_request_for_a_running_server_does_not_create_a_launch_thread(monkeypatch):
    instance = ServerInstance.__new__(ServerInstance)
    instance.server_id = "server-1"
    instance.check_running = lambda: True
    thread = Mock()
    monkeypatch.setattr("app.classes.shared.server.threading.Thread", thread)

    assert instance.run_threaded_server(user_id=1) is False
    thread.assert_not_called()


def test_statistics_jobs_are_replaced_after_a_confirmed_server_start():
    instance = ServerInstance.__new__(ServerInstance)
    instance.server_id = "server-1"
    instance.name = "Example Server"
    instance.server_scheduler = SimpleNamespace(add_job=Mock())

    instance._ensure_statistics_jobs()

    assert instance.server_scheduler.add_job.call_count == 2
    stats_call, save_call = instance.server_scheduler.add_job.call_args_list
    assert stats_call.kwargs == {
        "seconds": 5,
        "id": "stats_server-1",
        "replace_existing": True,
    }
    assert save_call.kwargs == {
        "seconds": 30,
        "id": "save_stats_server-1",
        "replace_existing": True,
    }


@pytest.mark.parametrize("handler_type", [BaseHandler, WebSocketHandler])
def test_forwarded_ip_headers_require_a_trusted_proxy(handler_type):
    handler = handler_type.__new__(handler_type)
    handler.helper = SimpleNamespace(
        get_setting=lambda key, default: ["127.0.0.1"] if key == "trusted_proxies" else default
    )
    handler.request = SimpleNamespace(
        remote_ip="198.51.100.20",
        headers={"X-Forwarded-For": "203.0.113.10"},
    )

    assert handler.get_remote_ip() == "198.51.100.20"

    handler.request.remote_ip = "127.0.0.1"
    handler.request.headers = {"X-Forwarded-For": "203.0.113.10, 127.0.0.1"}

    assert handler.get_remote_ip() == "203.0.113.10"


def test_trusted_proxy_config_is_validated_as_a_list():
    trusted_proxies = config_json_schema["properties"]["trusted_proxies"]
    assert trusted_proxies["type"] == "array"
    assert trusted_proxies["items"] == {"type": "string", "format": "ip"}


def test_release_411_xss_fixes_use_text_nodes_for_untrusted_content():
    activity_source = (
        PROJECT_ROOT / "app" / "frontend" / "templates" / "panel" / "activity_logs.html"
    ).read_text(encoding="utf-8")
    webhooks_source = (
        PROJECT_ROOT / "app" / "frontend" / "templates" / "panel" / "server_webhooks.html"
    ).read_text(encoding="utf-8")

    assert "row.append($('<td>').text(value.log_msg));" in activity_source
    assert "${value.log_msg}" not in activity_source
    assert webhooks_source.count('message: $("<div>").text(responseData.error_data || responseData.error)') == 2
