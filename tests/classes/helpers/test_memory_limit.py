import pytest

from app.classes.helpers.memory_limit import (
    MemoryLimitValidationError,
    canonicalize_memory_limit_mib,
    validate_java_heap_sizes,
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


def test_java_heap_mib_values_are_used_without_conversion():
    assert validate_java_heap_sizes("1024", "8192", 16_000) == (1024, 8192)


@pytest.mark.parametrize(
    ("minimum", "maximum", "limit"),
    [
        (2048, 1024, 0),
        (1024, 16_000, 8_000),
        (0, 1024, 0),
        (1024, "not-a-number", 0),
        (1024.5, 2048, 0),
    ],
)
def test_java_heap_validation_rejects_invalid_or_unachievable_values(
    minimum, maximum, limit
):
    with pytest.raises(MemoryLimitValidationError):
        validate_java_heap_sizes(minimum, maximum, limit)
