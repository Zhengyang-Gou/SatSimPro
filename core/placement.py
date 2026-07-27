"""Deterministic placement helpers for the two-host 60x20 constellation."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence


DEFAULT_HOST_ORBIT_RANGES = (
    {"name": "gzy0", "orbit_start": 1, "orbit_end": 30},
    {"name": "gzy1", "orbit_start": 31, "orbit_end": 60},
)


def host_for_orbit(
    orbit_number: int,
    host_ranges: Sequence[Mapping[str, Any]] = DEFAULT_HOST_ORBIT_RANGES,
) -> Optional[str]:
    orbit_number = int(orbit_number)
    for host_range in host_ranges:
        if int(host_range["orbit_start"]) <= orbit_number <= int(host_range["orbit_end"]):
            return str(host_range["name"])
    return None


def host_for_satellite(
    satellite: Any,
    host_ranges: Sequence[Mapping[str, Any]] = DEFAULT_HOST_ORBIT_RANGES,
) -> Optional[str]:
    return host_for_orbit(int(satellite.plane_idx) + 1, host_ranges)


def link_scope(
    source: Any,
    target: Any,
    host_ranges: Sequence[Mapping[str, Any]] = DEFAULT_HOST_ORBIT_RANGES,
) -> str:
    source_host = host_for_satellite(source, host_ranges)
    target_host = host_for_satellite(target, host_ranges)
    if source_host is None or target_host is None:
        return "unassigned"
    return "local" if source_host == target_host else "cross_host"


def normalize_host_ranges(host_ranges: Iterable[Mapping[str, Any]]):
    normalized = [
        {
            "name": str(item["name"]),
            "orbit_start": int(item["orbit_start"]),
            "orbit_end": int(item["orbit_end"]),
        }
        for item in host_ranges
    ]
    return tuple(sorted(normalized, key=lambda item: (item["orbit_start"], item["name"])))
