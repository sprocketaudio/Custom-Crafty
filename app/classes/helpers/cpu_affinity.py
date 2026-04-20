import os
import sys
import typing as t


class CpuAffinityValidationError(ValueError):
    """Raised when a CPU affinity string is invalid."""


def get_effective_cpu_set() -> t.Optional[t.Set[int]]:
    """Return effective allowed CPUs for this process, or None if unavailable."""
    if not sys.platform.startswith("linux"):
        return None
    if not hasattr(os, "sched_getaffinity"):
        return None
    return set(os.sched_getaffinity(0))


def _parse_non_negative_int(raw: str) -> int:
    if not raw or not raw.isdigit():
        raise CpuAffinityValidationError(f"Invalid CPU id token '{raw}'.")
    return int(raw)


def _add_cpu_id(
    cpu_id: int, seen: t.Set[int], ordered: t.List[int], segment: str
) -> None:
    if cpu_id in seen:
        raise CpuAffinityValidationError(
            f"Duplicate CPU id '{cpu_id}' in segment '{segment}'."
        )
    seen.add(cpu_id)
    ordered.append(cpu_id)


def canonicalize_cpu_affinity(
    raw_affinity: str, allowed_cpus: t.Optional[t.Set[int]] = None
) -> str:
    """
    Validate and canonicalize a CPU affinity string.

    Accepted forms:
    - single: 3
    - list: 1,4,7
    - range: 2-5
    - mixed: 0-3,8,10-12
    """
    normalized = (raw_affinity or "").strip()
    if normalized == "":
        return ""

    seen: t.Set[int] = set()
    ordered: t.List[int] = []
    segments = normalized.split(",")
    if not segments:
        raise CpuAffinityValidationError("CPU affinity cannot be empty.")

    for segment in segments:
        token = segment.strip()
        if token == "":
            raise CpuAffinityValidationError(
                "CPU affinity contains an empty segment."
            )

        if "-" in token:
            if token.count("-") != 1:
                raise CpuAffinityValidationError(
                    f"Invalid range segment '{token}'."
                )
            start_raw, end_raw = [part.strip() for part in token.split("-", 1)]
            start = _parse_non_negative_int(start_raw)
            end = _parse_non_negative_int(end_raw)
            if start > end:
                raise CpuAffinityValidationError(
                    f"Invalid range '{token}': start cannot exceed end."
                )
            for cpu_id in range(start, end + 1):
                _add_cpu_id(cpu_id, seen, ordered, token)
        else:
            cpu_id = _parse_non_negative_int(token)
            _add_cpu_id(cpu_id, seen, ordered, token)

    if allowed_cpus is not None:
        invalid_cpus = sorted(seen.difference(allowed_cpus))
        if invalid_cpus:
            invalid_list = ",".join(str(cpu) for cpu in invalid_cpus)
            raise CpuAffinityValidationError(
                f"CPU ids outside allowed set: {invalid_list}."
            )

    return _compact_cpu_ranges(sorted(ordered))


def _compact_cpu_ranges(sorted_cpu_ids: t.List[int]) -> str:
    if not sorted_cpu_ids:
        return ""

    segments: t.List[str] = []
    start = prev = sorted_cpu_ids[0]
    for cpu_id in sorted_cpu_ids[1:]:
        if cpu_id == prev + 1:
            prev = cpu_id
            continue
        segments.append(f"{start}-{prev}" if start != prev else str(start))
        start = prev = cpu_id

    segments.append(f"{start}-{prev}" if start != prev else str(start))
    return ",".join(segments)
