from __future__ import annotations

import math


class MemoryLimitValidationError(ValueError):
    """Raised when a memory limit value is invalid."""


def canonicalize_memory_limit_mib(raw_value) -> int:
    """Normalize a memory limit (MiB) to a non-negative integer.

    Empty values are treated as disabled (0).
    """
    if raw_value is None:
        return 0

    if isinstance(raw_value, bool):
        raise MemoryLimitValidationError("Memory limit must be an integer (MiB).")

    if isinstance(raw_value, str):
        trimmed = raw_value.strip()
        if trimmed == "":
            return 0
        raw_value = trimmed

    try:
        value = int(raw_value)
    except (TypeError, ValueError) as ex:
        raise MemoryLimitValidationError(
            "Memory limit must be an integer (MiB)."
        ) from ex

    if value < 0:
        raise MemoryLimitValidationError("Memory limit cannot be negative.")
    return value


def canonicalize_java_heap_gib(raw_value, field_name: str) -> int:
    """Convert a positive JVM heap value from GiB (the wizard unit) to MiB."""
    if isinstance(raw_value, bool):
        raise MemoryLimitValidationError(f"{field_name} must be a positive number (GiB).")

    try:
        value = float(raw_value)
    except (TypeError, ValueError) as ex:
        raise MemoryLimitValidationError(
            f"{field_name} must be a positive number (GiB)."
        ) from ex

    if not math.isfinite(value) or value <= 0:
        raise MemoryLimitValidationError(f"{field_name} must be a positive number (GiB).")
    return math.ceil(value * 1024)


def validate_java_heap_sizes(minimum_gib, maximum_gib, memory_limit_mib: int = 0) -> tuple[int, int]:
    """Validate wizard heap inputs and return their canonical MiB values."""
    minimum_mib = canonicalize_java_heap_gib(minimum_gib, "Minimum JVM memory")
    maximum_mib = canonicalize_java_heap_gib(maximum_gib, "Maximum JVM memory")
    if minimum_mib > maximum_mib:
        raise MemoryLimitValidationError(
            "Minimum JVM memory cannot exceed maximum JVM memory."
        )
    if memory_limit_mib and maximum_mib > memory_limit_mib:
        raise MemoryLimitValidationError(
            "Maximum JVM memory cannot exceed the server memory limit."
        )
    return minimum_mib, maximum_mib
