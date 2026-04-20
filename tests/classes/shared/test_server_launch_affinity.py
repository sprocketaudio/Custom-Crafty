import logging
from types import SimpleNamespace

import pytest

from app.classes.shared.server import ServerInstance
import app.classes.shared.server as server_module


def _build_server_instance(cpu_affinity: str, capability: dict) -> tuple:
    instance = ServerInstance.__new__(ServerInstance)
    instance.server_id = "srv-1"
    instance.name = "Affinity Test"
    instance.server_path = "/tmp/crafty-test"
    instance.server_command = ["java", "-jar", "server.jar", "nogui"]
    instance.settings = {
        "cpu_affinity": cpu_affinity,
        "type": "minecraft-java",
    }
    instance._active_launch_command = []
    instance._active_cpu_affinity = ""

    helper = SimpleNamespace()
    helper.launch_capabilities = {"cpu_affinity": capability}
    helper.detect_launch_capabilities = lambda: {"cpu_affinity": capability}
    instance.helper = helper

    launch_events = []
    start_errors = []

    def _log_launch_event(event_name, level=logging.INFO, **extra):
        launch_events.append(
            {
                "event": event_name,
                "level": level,
                **extra,
            }
        )

    def _notify_start_error(_user_id, _user_lang, detail, channel="send_error"):
        start_errors.append({"detail": detail, "channel": channel})

    instance._log_launch_event = _log_launch_event
    instance._notify_start_error = _notify_start_error
    return instance, launch_events, start_errors


def test_resolve_launch_command_returns_base_when_affinity_unset(monkeypatch):
    capability = {
        "supported": True,
        "taskset_path": "/usr/bin/taskset",
        "reason": "ok",
        "os": "linux",
    }
    instance, launch_events, start_errors = _build_server_instance("", capability)
    monkeypatch.setattr(server_module, "get_effective_cpu_set", lambda: {0, 1, 2, 3})

    resolved = instance._resolve_launch_command(user_id=1, user_lang="en")

    assert resolved == ["java", "-jar", "server.jar", "nogui"]
    assert instance._active_cpu_affinity == ""
    assert launch_events == []
    assert start_errors == []


def test_resolve_launch_command_applies_taskset_prefix(monkeypatch):
    capability = {
        "supported": True,
        "taskset_path": "/usr/bin/taskset",
        "reason": "ok",
        "os": "linux",
    }
    instance, launch_events, start_errors = _build_server_instance("3,1-2", capability)
    monkeypatch.setattr(server_module, "get_effective_cpu_set", lambda: {0, 1, 2, 3})

    resolved = instance._resolve_launch_command(user_id=1, user_lang="en")

    assert resolved == [
        "/usr/bin/taskset",
        "--cpu-list",
        "1-3",
        "java",
        "-jar",
        "server.jar",
        "nogui",
    ]
    assert instance._active_cpu_affinity == "1-3"
    assert launch_events[-1]["event"] == "cpu_affinity_applied"
    assert launch_events[-1]["canonical_cpu_affinity"] == "1-3"
    assert start_errors == []


def test_resolve_launch_command_blocks_when_capability_unsupported(monkeypatch):
    capability = {
        "supported": False,
        "taskset_path": None,
        "reason": "non_linux_host",
        "os": "win32",
    }
    instance, launch_events, start_errors = _build_server_instance("0-1", capability)
    monkeypatch.setattr(server_module, "get_effective_cpu_set", lambda: {0, 1, 2, 3})

    resolved = instance._resolve_launch_command(user_id=1, user_lang="en")

    assert resolved is None
    assert launch_events[-1]["event"] == "launch_blocked"
    assert launch_events[-1]["reason"] == "cpu_affinity_unsupported"
    assert start_errors[-1]["detail"] == "CPU affinity requires Linux + taskset."


def test_resolve_launch_command_blocks_when_taskset_missing(monkeypatch):
    capability = {
        "supported": True,
        "taskset_path": None,
        "reason": "ok",
        "os": "linux",
    }
    instance, launch_events, start_errors = _build_server_instance("0-1", capability)
    monkeypatch.setattr(server_module, "get_effective_cpu_set", lambda: {0, 1, 2, 3})
    monkeypatch.setattr(server_module.shutil, "which", lambda _name: None)

    resolved = instance._resolve_launch_command(user_id=1, user_lang="en")

    assert resolved is None
    assert launch_events[-1]["event"] == "launch_blocked"
    assert launch_events[-1]["reason"] == "cpu_affinity_taskset_missing"
    assert (
        start_errors[-1]["detail"]
        == "CPU affinity requires taskset but it is unavailable."
    )


@pytest.mark.parametrize("raw_affinity", ["-1", "2-1", "1,,2", "abc"])
def test_resolve_launch_command_blocks_when_affinity_invalid(monkeypatch, raw_affinity):
    capability = {
        "supported": True,
        "taskset_path": "/usr/bin/taskset",
        "reason": "ok",
        "os": "linux",
    }
    instance, launch_events, start_errors = _build_server_instance(raw_affinity, capability)
    monkeypatch.setattr(server_module, "get_effective_cpu_set", lambda: {0, 1, 2, 3})

    resolved = instance._resolve_launch_command(user_id=1, user_lang="en")

    assert resolved is None
    assert launch_events[-1]["event"] == "launch_blocked"
    assert launch_events[-1]["reason"] == "invalid_cpu_affinity"
    assert start_errors[-1]["detail"].startswith("CPU affinity is invalid:")


def test_log_effective_cpu_affinity_state_logs_verified_value(monkeypatch):
    capability = {
        "supported": True,
        "taskset_path": "/usr/bin/taskset",
        "reason": "ok",
        "os": "linux",
    }
    instance, launch_events, _start_errors = _build_server_instance("0-1", capability)
    instance._active_cpu_affinity = "0-1"
    instance.process = SimpleNamespace(pid=1234)
    monkeypatch.setattr(instance, "_read_effective_cpu_affinity", lambda _pid: "0-1")

    instance._log_effective_cpu_affinity_state()

    assert launch_events[-1]["event"] == "cpu_affinity_verify"
    assert launch_events[-1]["pid"] == 1234
    assert launch_events[-1]["effective_cpu_affinity"] == "0-1"


def test_log_effective_cpu_affinity_state_logs_unavailable_when_unreadable(monkeypatch):
    capability = {
        "supported": True,
        "taskset_path": "/usr/bin/taskset",
        "reason": "ok",
        "os": "linux",
    }
    instance, launch_events, _start_errors = _build_server_instance("0-1", capability)
    instance._active_cpu_affinity = "0-1"
    instance.process = SimpleNamespace(pid=1234)
    monkeypatch.setattr(instance, "_read_effective_cpu_affinity", lambda _pid: None)

    instance._log_effective_cpu_affinity_state()

    assert launch_events[-1]["event"] == "cpu_affinity_verify_unavailable"
    assert launch_events[-1]["pid"] == 1234
