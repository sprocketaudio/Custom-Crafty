import logging
from types import SimpleNamespace
from pathlib import Path

import pytest

import app.classes.shared.server as server_module
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


def test_configure_memory_limit_cgroup_enables_memory_controller_for_children(tmp_path):
    capability = {
        "supported": True,
        "reason": "ok",
        "os": "linux",
        "cgroup_root": str(tmp_path / "crafty"),
    }
    instance, _launch_events, _start_errors = _build_server_instance(1024, capability)

    cgroup_root = Path(capability["cgroup_root"])
    cgroup_root.mkdir(parents=True)
    (cgroup_root / "cgroup.subtree_control").write_text("", encoding="utf-8")

    cgroup_path, memory_limit_bytes = instance._configure_memory_limit_cgroup(1024, capability)

    assert memory_limit_bytes == 1024 * 1024 * 1024
    assert (cgroup_root / "cgroup.subtree_control").read_text(encoding="utf-8") == "+memory"
    assert Path(cgroup_path, "memory.max").read_text(encoding="utf-8") == str(memory_limit_bytes)


def test_get_memory_limit_capability_refreshes_cached_unsupported_result():
    stale_capability = {
        "supported": False,
        "reason": "cgroup_root_unwritable",
        "os": "linux",
        "cgroup_root": "/sys/fs/cgroup/crafty",
    }
    refreshed_capability = {
        "supported": True,
        "reason": "ok",
        "os": "linux",
        "cgroup_root": "/sys/fs/cgroup/system.slice/custom-crafty.service/crafty",
    }
    instance, _launch_events, _start_errors = _build_server_instance(1024, stale_capability)
    instance.helper.launch_capabilities = {"memory_limit": stale_capability}
    instance.helper.detect_launch_capabilities = lambda: {"memory_limit": refreshed_capability}

    result = instance._get_memory_limit_capability()

    assert result == refreshed_capability


def test_failed_forge_installer_clears_import_status_without_reconfiguring(monkeypatch):
    instance = ServerInstance.__new__(ServerInstance)
    instance.server_id = "srv-forge-failure"
    instance.process = SimpleNamespace(poll=lambda: 1)
    completed_imports = []
    instance.stats_helper = SimpleNamespace(
        finish_import=lambda: completed_imports.append(True)
    )

    monkeypatch.setattr(
        server_module.PermissionsServers,
        "get_server_user_list",
        lambda _server_id: [],
    )
    monkeypatch.setattr(
        server_module.HelperServers,
        "get_server_obj",
        lambda _server_id: pytest.fail("failed installer must not reconfigure server"),
    )

    instance.forge_install_watcher()

    assert completed_imports == [True]


@pytest.mark.parametrize(
    ("installer_name", "expected"),
    [
        ("forge-installer-1.20.1-47.4.13.jar", ("forge", "1.20.1-47.4.13")),
        ("forge-1.20.1-47.4.13-installer.jar", ("forge", "1.20.1-47.4.13")),
        ("neoforge-installer-21.1.140.jar", ("neoforge", "21.1.140")),
        ("neoforge-21.1.140-installer.jar", ("neoforge", "21.1.140")),
    ],
)
def test_loader_info_from_installer_name(installer_name, expected):
    assert ServerInstance._loader_info_from_installer_name(installer_name) == expected


def test_loader_info_rejects_invalid_installer_name():
    assert ServerInstance._loader_info_from_installer_name("server.jar") is None


def test_successful_forge_installer_saves_launcher_before_deleting_installer(
    monkeypatch, tmp_path
):
    installer_name = "forge-installer-1.20.1-47.4.13.jar"
    installer_path = tmp_path / installer_name
    installer_path.write_text("installer", encoding="utf-8")
    instance = ServerInstance.__new__(ServerInstance)
    instance.server_id = "srv-forge-success"
    instance.process = SimpleNamespace(poll=lambda: 0)
    completed_imports = []
    instance.stats_helper = SimpleNamespace(
        finish_import=lambda: completed_imports.append(True)
    )
    server_obj = SimpleNamespace(path=str(tmp_path), executable=installer_name)
    configured = []

    monkeypatch.setattr(
        server_module.HelperServers,
        "get_server_obj",
        lambda _server_id: server_obj,
    )
    monkeypatch.setattr(
        server_module.PermissionsServers,
        "get_server_user_list",
        lambda _server_id: [],
    )
    monkeypatch.setattr(
        instance,
        "_update_loader_launch_config",
        lambda root, kind, version: configured.append((root, kind, version)),
    )

    instance.forge_install_watcher()

    assert configured == [(tmp_path, "forge", "1.20.1-47.4.13")]
    assert not installer_path.exists()
    assert completed_imports == [True]


def test_start_recovers_missing_installer_with_generated_loader_files(tmp_path):
    instance = ServerInstance.__new__(ServerInstance)
    instance.server_id = "srv-forge-recovery"
    instance.helper = SimpleNamespace(is_os_windows=lambda: False)
    instance.settings = {
        "path": str(tmp_path),
        "executable": "forge-installer-1.20.1-47.4.13.jar",
        "execution_command": "java -jar forge-installer-1.20.1-47.4.13.jar",
    }
    generated_executable = (
        "libraries/net/minecraftforge/forge/1.20.1-47.4.13/"
        "forge-1.20.1-47.4.13-server.jar"
    )
    generated_path = tmp_path / generated_executable
    generated_path.parent.mkdir(parents=True)
    generated_path.write_text("", encoding="utf-8")
    recovered = []

    def recover_loader_config(_root, kind, version):
        recovered.append((kind, version))
        instance.settings["executable"] = generated_executable
        instance.settings["execution_command"] = (
            "java @user_jvm_args.txt "
            "@libraries/net/minecraftforge/forge/1.20.1-47.4.13/unix_args.txt nogui"
        )

    instance._update_loader_launch_config = recover_loader_config

    instance.setup_server_run_command()

    assert recovered == [("forge", "1.20.1-47.4.13")]
    assert instance.server_command == [
        "java",
        "@user_jvm_args.txt",
        "@libraries/net/minecraftforge/forge/1.20.1-47.4.13/unix_args.txt",
        "nogui",
    ]


@pytest.mark.parametrize(
    ("loader_kind", "version", "executable"),
    [
        (
            "forge",
            "1.20.1-47.4.13",
            "libraries/net/minecraftforge/forge/1.20.1-47.4.13/"
            "forge-1.20.1-47.4.13-server.jar",
        ),
        (
            "neoforge",
            "21.1.140",
            "libraries/net/neoforged/neoforge/21.1.140/"
            "neoforge-21.1.140-server.jar",
        ),
    ],
)
def test_loader_launch_config_uses_generated_args_file(
    monkeypatch, tmp_path, loader_kind, version, executable
):
    args_rel = (
        f"libraries/net/{'minecraftforge/forge' if loader_kind == 'forge' else 'neoforged/neoforge'}"
        f"/{version}/unix_args.txt"
    )
    args_path = tmp_path / args_rel
    args_path.parent.mkdir(parents=True)
    args_path.write_text("", encoding="utf-8")
    executable_path = tmp_path / executable
    executable_path.parent.mkdir(parents=True, exist_ok=True)
    executable_path.write_text("", encoding="utf-8")

    instance = ServerInstance.__new__(ServerInstance)
    instance.server_id = "srv-loader"
    instance.settings = {"execution_command": "java -jar old-installer.jar"}
    instance.helper = SimpleNamespace(is_os_windows=lambda: False)
    instance.reload_server_settings = lambda: None
    server_obj = SimpleNamespace(executable="old-installer.jar", execution_command="")
    saved = []

    monkeypatch.setattr(
        server_module.HelperServers,
        "get_server_obj",
        lambda _server_id: server_obj,
    )
    monkeypatch.setattr(
        server_module.HelperServers,
        "update_server",
        lambda obj: saved.append(obj),
    )

    instance._update_loader_launch_config(tmp_path, loader_kind, version)

    assert server_obj.executable == executable
    assert server_obj.execution_command == f"java @user_jvm_args.txt @{args_rel} nogui"
    assert saved == [server_obj]
