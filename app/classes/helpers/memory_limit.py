from __future__ import annotations


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

