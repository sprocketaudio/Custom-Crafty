import pytest

from app.classes.helpers.memory_limit import (
    MemoryLimitValidationError,
    canonicalize_memory_limit_mib,
)


@pytest.mark.parametrize(
    "raw_value, expected",
    [
        (None, 0),
        ("", 0),
        ("  ", 0),
        (0, 0),
        ("0", 0),
        (1024, 1024),
        ("2048", 2048),
    ],
)
def test_canonicalize_memory_limit_mib_valid(raw_value, expected):
    assert canonicalize_memory_limit_mib(raw_value) == expected


@pytest.mark.parametrize("raw_value", [-1, "-1", "1.5", "abc", True, False])
def test_canonicalize_memory_limit_mib_invalid(raw_value):
    with pytest.raises(MemoryLimitValidationError):
        canonicalize_memory_limit_mib(raw_value)

