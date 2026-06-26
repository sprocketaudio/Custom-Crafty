import os
from pathlib import Path
from types import SimpleNamespace

from app.classes.helpers import helpers as helpers_module
from app.classes.helpers.helpers import Helpers


def test_detect_launch_capabilities_supports_writable_memory_cgroup(monkeypatch, tmp_path):
    fake_cgroup_root = tmp_path / "sys_fs_cgroup"
    fake_cgroup_root.mkdir()
    (fake_cgroup_root / "cgroup.controllers").write_text(
        "cpuset cpu io memory pids",
        encoding="utf-8",
    )

    real_path = Path

    def fake_path(*parts):
        joined = os.path.join(*(str(part) for part in parts))
        if joined.startswith("/sys/fs/cgroup"):
            suffix = joined.removeprefix("/sys/fs/cgroup").lstrip("/\\")
            return real_path(fake_cgroup_root / suffix)
        return real_path(joined)

    monkeypatch.setattr("app.classes.helpers.helpers.sys.platform", "linux")
    monkeypatch.setattr(
        "app.classes.helpers.helpers.shutil.which", lambda _name: "/usr/bin/taskset"
    )
    monkeypatch.setattr(
        helpers_module,
        "pathlib",
        SimpleNamespace(Path=fake_path),
    )
    monkeypatch.delenv("CRAFTY_MEMORY_CGROUP_ROOT", raising=False)

    helper = Helpers.__new__(Helpers)
    helper.launch_capabilities = {}

    capabilities = helper.detect_launch_capabilities()

    assert capabilities["memory_limit"]["supported"] is True
    assert capabilities["memory_limit"]["reason"] == "ok"
    assert not list((fake_cgroup_root / "crafty").glob(".crafty_probe_*"))
