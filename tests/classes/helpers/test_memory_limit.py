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


def test_java_heap_gib_values_are_converted_to_mib():
    assert validate_java_heap_sizes("1", "8", 16_000) == (1024, 8192)


@pytest.mark.parametrize(
    ("minimum", "maximum", "limit"),
    [
        (2, 1, 0),
        (1, 16, 8_000),
        (0, 1, 0),
        (1, "not-a-number", 0),
    ],
)
def test_java_heap_validation_rejects_invalid_or_unachievable_values(
    minimum, maximum, limit
):
    with pytest.raises(MemoryLimitValidationError):
        validate_java_heap_sizes(minimum, maximum, limit)
