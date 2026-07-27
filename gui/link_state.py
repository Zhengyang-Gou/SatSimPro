"""Small helpers and type aliases for link state shared by GUI modules."""

from typing import Any, Dict, Iterable, List, Tuple

import numpy as np

from core.placement import host_for_satellite

from .theme import DOWN

LinkKey = Tuple[int, int]
LinkRecord = Dict[str, Any]


def link_key(src: int, tgt: int) -> LinkKey:
    """Return a stable, direction-independent key for one ISL."""
    return (src, tgt) if src < tgt else (tgt, src)


def directed_link_key(src: int, tgt: int) -> LinkKey:
    """Return a direction-sensitive key for one Redis-facing link."""
    return (src, tgt)


def remote_sat_id(sat: Any) -> int:
    """Return the satellite id used by the remote container/Redis scripts."""
    return 10000 + (sat.plane_idx + 1) * 100 + (sat.node_idx + 1)


def remote_host_name(sat: Any, host_ranges=None) -> str:
    """Return the backend owning a satellite, or ``unassigned``."""
    if host_ranges is None:
        return host_for_satellite(sat) or "unassigned"
    return host_for_satellite(sat, host_ranges) or "unassigned"


def is_down(value: Any) -> bool:
    return str(value).lower() == DOWN


def satellite_positions_array(satellites: Iterable[Any]) -> np.ndarray:
    if not isinstance(satellites, list):
        satellites = list(satellites)
    if not satellites:
        return np.empty((0, 3), dtype=np.float64)
    return np.asarray([s.position for s in satellites], dtype=np.float64)


def link_pairs_to_lines(link_pairs: Iterable[LinkKey]) -> np.ndarray:
    lines: List[int] = []
    for src, tgt in sorted(link_pairs):
        lines.extend([2, int(src), int(tgt)])
    return np.asarray(lines, dtype=np.int64) if lines else np.empty((0,), dtype=np.int64)
