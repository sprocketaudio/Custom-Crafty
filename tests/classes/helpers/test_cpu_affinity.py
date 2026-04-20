import pytest

from app.classes.helpers.cpu_affinity import (
    CpuAffinityValidationError,
    canonicalize_cpu_affinity,
)


@pytest.mark.parametrize(
    ("raw_affinity", "expected"),
    [
        ("", ""),
        ("0-3", "0-3"),
        ("4,6,8,10", "4,6,8,10"),
        ("2-5,9-11", "2-5,9-11"),
        (" 4, 2-3 ", "2-4"),
        ("0,2,1", "0-2"),
        ("7", "7"),
    ],
)
def test_canonicalize_cpu_affinity_valid(raw_affinity: str, expected: str) -> None:
    assert canonicalize_cpu_affinity(raw_affinity) == expected


@pytest.mark.parametrize(
    "raw_affinity",
    [
        "1,,2",
        "7-3",
        "-1",
        "1-",
        "a",
        "1,1",
        "1-3,2",
        "1-2-3",
    ],
)
def test_canonicalize_cpu_affinity_invalid(raw_affinity: str) -> None:
    with pytest.raises(CpuAffinityValidationError):
        canonicalize_cpu_affinity(raw_affinity)


def test_canonicalize_cpu_affinity_rejects_out_of_allowed_set() -> None:
    with pytest.raises(CpuAffinityValidationError):
        canonicalize_cpu_affinity("0-2,4", allowed_cpus={0, 1, 2, 3})


def test_canonicalize_cpu_affinity_accepts_allowed_set() -> None:
    assert canonicalize_cpu_affinity("3,1-2,0", allowed_cpus={0, 1, 2, 3}) == "0-3"
