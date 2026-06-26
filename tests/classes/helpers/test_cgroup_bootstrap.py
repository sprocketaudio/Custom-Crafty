import os
from types import SimpleNamespace

from app.classes.helpers import helpers as helpers_module
from app.classes.helpers.helpers import Helpers


def test_prepare_memory_cgroup_root_moves_process_and_enables_memory_controller(
    monkeypatch, tmp_path
):
    fake_cgroup_root = tmp_path / "sys_fs_cgroup"
    fake_cgroup_root.mkdir()
    service_cgroup = fake_cgroup_root / "system.slice" / "custom-crafty.service"
    service_cgroup.mkdir(parents=True)
    (service_cgroup / "cgroup.procs").write_text("", encoding="utf-8")
    (service_cgroup / "cgroup.subtree_control").write_text("", encoding="utf-8")

    crafty_root = service_cgroup / "crafty"
    monkeypatch.setenv(
        "CRAFTY_MEMORY_CGROUP_ROOT",
        "/sys/fs/cgroup/system.slice/custom-crafty.service/crafty",
    )
    monkeypatch.setattr("app.classes.helpers.helpers.sys.platform", "linux")
    monkeypatch.setattr("app.classes.helpers.helpers.os.getpid", lambda: 4321)

    real_path = helpers_module.pathlib.Path

    def fake_path(*parts):
        joined = os.path.join(*(str(part) for part in parts))
        if joined.startswith("/sys/fs/cgroup"):
            suffix = joined.removeprefix("/sys/fs/cgroup").lstrip("/\\")
            return real_path(fake_cgroup_root / suffix)
        return real_path(joined)

    monkeypatch.setattr(
        helpers_module,
        "pathlib",
        SimpleNamespace(Path=fake_path),
    )
    monkeypatch.setattr(
        Helpers,
        "get_self_cgroup_v2_path",
        staticmethod(lambda: str(service_cgroup)),
    )

    helper = Helpers.__new__(Helpers)

    assert helper.prepare_memory_cgroup_root() is True
    assert (service_cgroup / "cgroup.subtree_control").read_text(encoding="utf-8") == "+memory"
    assert crafty_root.exists()
