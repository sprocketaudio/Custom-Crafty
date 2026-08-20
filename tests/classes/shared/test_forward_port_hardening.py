import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.classes.shared.server import ServerInstance
from app.classes.shared.tasks import TasksManager
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
