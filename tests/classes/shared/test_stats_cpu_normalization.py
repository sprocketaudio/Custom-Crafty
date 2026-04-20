from contextlib import nullcontext

import app.classes.remote_stats.stats as stats_module
from app.classes.remote_stats.stats import Stats


class _FakePsutilProcess:
    def __init__(
        self,
        measured_cpu_percent,
        affinity=None,
        affinity_error=None,
        memory_bytes=0,
    ):
        self._measured_cpu_percent = measured_cpu_percent
        self._affinity = affinity
        self._affinity_error = affinity_error
        self._memory_bytes = memory_bytes

    def cpu_percent(self, interval=None):
        if interval is None:
            return 0.0
        return float(self._measured_cpu_percent)

    def cpu_affinity(self):
        if self._affinity_error is not None:
            raise self._affinity_error
        return self._affinity

    def memory_info(self):
        return (self._memory_bytes,)

    def memory_percent(self):
        return 0.0

    def oneshot(self):
        return nullcontext()


def test_process_cpu_usage_normalizes_to_process_affinity_capacity(monkeypatch):
    fake_process = _FakePsutilProcess(
        measured_cpu_percent=400.0,
        affinity=[0, 1, 2, 3],
    )
    monkeypatch.setattr(stats_module.psutil, "Process", lambda _pid: fake_process)
    monkeypatch.setattr(stats_module.psutil, "cpu_count", lambda: 16)

    process_wrapper = type("P", (), {"pid": 1234})()
    stats = Stats._get_process_stats(process_wrapper)

    # 400% across 4 allowed CPUs should render as 100%.
    assert stats["cpu_usage"] == 100.0
    assert stats["cpu_capacity_cores"] == 4


def test_process_cpu_usage_falls_back_to_host_cpu_count_when_affinity_unavailable(
    monkeypatch,
):
    fake_process = _FakePsutilProcess(
        measured_cpu_percent=400.0,
        affinity_error=NotImplementedError(),
    )
    monkeypatch.setattr(stats_module.psutil, "Process", lambda _pid: fake_process)
    monkeypatch.setattr(stats_module.psutil, "cpu_count", lambda: 16)

    process_wrapper = type("P", (), {"pid": 1234})()
    stats = Stats._get_process_stats(process_wrapper)

    # Fallback keeps legacy normalization semantics.
    assert stats["cpu_usage"] == 25.0
    assert stats["cpu_capacity_cores"] == 16


def test_process_memory_usage_normalizes_to_configured_capacity(monkeypatch):
    fake_process = _FakePsutilProcess(
        measured_cpu_percent=0.0,
        affinity=[0, 1, 2, 3],
        memory_bytes=536870912,  # 512 MiB
    )
    monkeypatch.setattr(stats_module.psutil, "Process", lambda _pid: fake_process)
    monkeypatch.setattr(stats_module.psutil, "cpu_count", lambda: 16)

    process_wrapper = type("P", (), {"pid": 1234})()
    stats = Stats._get_process_stats(
        process_wrapper,
        memory_capacity_bytes=1073741824,  # 1 GiB
    )

    assert stats["mem_percentage"] == 50.0
    assert stats["memory_capacity_raw"] == 1073741824


def test_process_memory_usage_falls_back_to_host_total_when_capacity_missing(monkeypatch):
    fake_process = _FakePsutilProcess(
        measured_cpu_percent=0.0,
        affinity=[0, 1, 2, 3],
        memory_bytes=536870912,  # 512 MiB
    )
    monkeypatch.setattr(stats_module.psutil, "Process", lambda _pid: fake_process)
    monkeypatch.setattr(stats_module.psutil, "cpu_count", lambda: 16)
    monkeypatch.setattr(
        stats_module.psutil,
        "virtual_memory",
        lambda: type("VM", (), {"total": 2147483648})(),  # 2 GiB
    )

    process_wrapper = type("P", (), {"pid": 1234})()
    stats = Stats._get_process_stats(process_wrapper)

    assert stats["mem_percentage"] == 25.0
    assert stats["memory_capacity_raw"] == 2147483648
