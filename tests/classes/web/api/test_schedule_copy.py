import json
from types import SimpleNamespace
from unittest.mock import Mock

from app.classes.web.routes.api.servers.server.tasks.copy import (
    ApiServersServerTasksCopyHandler,
)


def _handler(source_server_id: str):
    handler = ApiServersServerTasksCopyHandler.__new__(ApiServersServerTasksCopyHandler)
    handler.request = SimpleNamespace(
        body=json.dumps({"source_server_id": source_server_id}).encode()
    )
    handler.authenticate_user = lambda: ([], None, None, None, {"user_id": 1})
    handler.finish_json = lambda status, body: (status, body)
    return handler


def test_copy_schedules_rejects_the_destination_as_its_own_source():
    handler = _handler("target-server")

    status, body = handler.post("target-server")

    assert status == 400
    assert body["error"] == "INVALID_COPY_SOURCE"


def test_copy_schedules_rejects_backup_schedules_before_replacing_target():
    handler = _handler("source-server")
    remove_all_server_tasks = Mock()
    handler.tasks_manager = SimpleNamespace(remove_all_server_tasks=remove_all_server_tasks)
    handler._has_schedule_permission = lambda *_args: True
    handler.controller = SimpleNamespace(
        management=SimpleNamespace(
            get_schedules_by_server=lambda _server_id: [
                SimpleNamespace(action="backup_server")
            ]
        )
    )

    status, body = handler.post("target-server")

    assert status == 409
    assert body["error"] == "SERVER_SPECIFIC_BACKUP_SCHEDULE"
    remove_all_server_tasks.assert_not_called()
