import logging
from types import SimpleNamespace

import pytest

from app.classes.shared.server import ServerInstance


def _build_server_instance(memory_limit_mib, capability: dict) -> tuple:
    instance = ServerInstance.__new__(ServerInstance)
    instance.server_id = "srv-memory"
    instance.name = "Memory Limit Test"
    instance.server_path = "/tmp/crafty-test"
    instance.server_command = ["java", "-jar", "server.jar", "nogui"]
    instance.settings = {
        "memory_limit_mib": memory_limit_mib,
        "type": "minecraft-java",
    }
    instance.process = None
    instance._active_launch_command = []
    instance._active_cpu_affinity = ""
    instance._active_memory_limit_mib = 0
    instance._active_memory_limit_bytes = 0
    instance._active_memory_cgroup_path = ""

    helper = SimpleNamespace()
    helper.launch_capabilities = {"memory_limit": capability}
    helper.detect_launch_capabilities = lambda: {"memory_limit": capability}
    instance.helper = helper
    instance.stats_helper = SimpleNamespace(finish_import=lambda: None)

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


def test_prepare_memory_limit_policy_no_limit_configured():
    capability = {
        "supported": True,
        "reason": "ok",
        "os": "linux",
        "cgroup_root": "/sys/fs/cgroup/crafty",
    }
    instance, launch_events, start_errors = _build_server_instance(0, capability)

    result = instance._prepare_memory_limit_policy(user_id=1, user_lang="en")

    assert result is True
    assert instance._active_memory_limit_mib == 0
    assert launch_events == []
    assert start_errors == []


def test_prepare_memory_limit_policy_blocks_when_invalid_value():
    capability = {
        "supported": True,
        "reason": "ok",
        "os": "linux",
        "cgroup_root": "/sys/fs/cgroup/crafty",
    }
    instance, launch_events, start_errors = _build_server_instance("-1", capability)

    result = instance._prepare_memory_limit_policy(user_id=1, user_lang="en")

    assert result is False
    assert launch_events[-1]["reason"] == "invalid_memory_limit"
    assert start_errors[-1]["detail"].startswith("Memory limit is invalid:")


def test_prepare_memory_limit_policy_blocks_when_capability_unsupported():
    capability = {
        "supported": False,
        "reason": "non_linux_host",
        "os": "win32",
        "cgroup_root": "",
    }
    instance, launch_events, start_errors = _build_server_instance(1024, capability)

    result = instance._prepare_memory_limit_policy(user_id=1, user_lang="en")

    assert result is False
    assert launch_events[-1]["reason"] == "memory_limit_unsupported"
    assert start_errors[-1]["detail"].startswith("Memory limit requires Linux")


def test_prepare_memory_limit_policy_applies_configured_limit(monkeypatch):
    capability = {
        "supported": True,
        "reason": "ok",
        "os": "linux",
        "cgroup_root": "/sys/fs/cgroup/crafty",
    }
    instance, launch_events, start_errors = _build_server_instance(1024, capability)

    monkeypatch.setattr(
        instance,
        "_configure_memory_limit_cgroup",
        lambda _mib, _caps: ("/sys/fs/cgroup/crafty/server-srv-memory", 1073741824),
    )

    result = instance._prepare_memory_limit_policy(user_id=1, user_lang="en")

    assert result is True
    assert instance._active_memory_limit_mib == 1024
    assert instance._active_memory_limit_bytes == 1073741824
    assert (
        instance._active_memory_cgroup_path
        == "/sys/fs/cgroup/crafty/server-srv-memory"
    )
    assert launch_events[-1]["event"] == "memory_limit_applied"
    assert start_errors == []


def test_attach_process_to_memory_cgroup_blocks_on_write_failure(monkeypatch):
    capability = {
        "supported": True,
        "reason": "ok",
        "os": "linux",
        "cgroup_root": "/sys/fs/cgroup/crafty",
    }
    instance, launch_events, start_errors = _build_server_instance(1024, capability)
    instance._active_memory_limit_mib = 1024
    instance._active_memory_limit_bytes = 1073741824
    instance._active_memory_cgroup_path = "/sys/fs/cgroup/crafty/server-srv-memory"
    instance.process = SimpleNamespace(pid=1234, kill=lambda: None)
    instance.cleanup_server_object = lambda: None

    def _raise(*_args, **_kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr("pathlib.Path.write_text", _raise)

    result = instance._attach_process_to_memory_cgroup(user_id=1, user_lang="en")

    assert result is False
    assert launch_events[-1]["reason"] == "memory_cgroup_attach_failed"
    assert "permission denied" in start_errors[-1]["detail"]

