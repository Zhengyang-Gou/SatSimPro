"""Offline per-satellite link-state dataset exporter."""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

import numpy as np

from link_info import generate_link_info

from .calculator import OrbitCalculator
from .placement import DEFAULT_HOST_ORBIT_RANGES, host_for_satellite, normalize_host_ranges
from .strategies import GridDeltaStrategy


SEPARATOR = "-" * 60
LIGHT_SPEED_KM_PER_S = 299792.458

LinkKey = Tuple[int, int]
ProgressCallback = Callable[[int, int], bool]


class LinkDatasetExportCancelled(Exception):
    """Raised when a user cancels offline dataset export."""


@dataclass
class LinkDatasetExportResult:
    output_dir: str
    file_count: int
    time_slices: int
    host_output_dirs: Dict[str, str] = field(default_factory=dict)


class RandomLinkFailureModel:
    """Per-link up-to-down process with blinking failure periods."""

    def __init__(
        self,
        *,
        enabled: bool,
        failure_probability: float,
        random_seed: int,
        min_down_slices: int = 2,
        max_down_slices: int = 8,
    ):
        self.enabled = enabled
        self.failure_probability = failure_probability
        self.rng = random.Random(random_seed)
        self.min_down_slices = min_down_slices
        self.max_down_slices = max_down_slices
        self.down_remaining: Dict[LinkKey, int] = {}
        self.blink_on: Dict[LinkKey, bool] = {}

    def step(self, candidate_keys: Iterable[LinkKey], active_keys: Set[LinkKey]) -> Set[LinkKey]:
        if not self.enabled:
            return set()

        down_keys: Set[LinkKey] = set()
        for key in candidate_keys:
            remaining = self.down_remaining.get(key, 0)
            if remaining > 0:
                blink_on = not self.blink_on.get(key, False)
                self.blink_on[key] = blink_on
                if blink_on:
                    down_keys.add(key)

                remaining -= 1
                if remaining > 0:
                    self.down_remaining[key] = remaining
                else:
                    self.down_remaining.pop(key, None)
                    self.blink_on.pop(key, None)
                continue

            if key in active_keys and self.rng.random() < self.failure_probability:
                duration = self.rng.randint(self.min_down_slices, self.max_down_slices)
                down_keys.add(key)
                if duration > 1:
                    self.down_remaining[key] = duration - 1
                    self.blink_on[key] = True

        return down_keys


class LinkDatasetExporter:
    """Generate Satellite Simulation-compatible satellite_*.txt files from the orbit model."""

    def export(
        self,
        *,
        orbit_num: int,
        sat_per_orbit: int,
        time_slices: int,
        duration_sec: float,
        output_dir: str,
        phase_factor: int = 0,
        altitude_km: float = 550.0,
        inclination_deg: float = 53.0,
        random_failure_enabled: bool = False,
        failure_probability: float = 0.0,
        random_seed: int = 42,
        strategy: Optional[Any] = None,
        start_time: Optional[datetime] = None,
        epoch_time: Optional[datetime] = None,
        progress_callback: Optional[ProgressCallback] = None,
        host_ranges: Optional[Iterable[Dict[str, Any]]] = None,
        bridge_by_host: Optional[Dict[str, str]] = None,
    ) -> LinkDatasetExportResult:
        self._validate(
            orbit_num=orbit_num,
            sat_per_orbit=sat_per_orbit,
            time_slices=time_slices,
            duration_sec=duration_sec,
            failure_probability=failure_probability,
            output_dir=output_dir,
        )

        current_time = start_time or datetime.utcnow()
        run_id = current_time.strftime("%Y%m%d_%H%M%S")
        walker_epoch_time = epoch_time or current_time
        strategy = strategy or GridDeltaStrategy()
        calculator = OrbitCalculator()
        calculator.generate_walker(
            orbit_num * sat_per_orbit,
            orbit_num,
            phase_factor,
            altitude_km,
            inclination_deg,
            walker_epoch_time,
        )

        calculator.propagate(current_time)
        strategy.compute_links(calculator.satellites)
        normalized_host_ranges = normalize_host_ranges(
            host_ranges or DEFAULT_HOST_ORBIT_RANGES
        )
        bridge_by_host = dict(
            bridge_by_host
            or {
                "gzy0": "brB",
                "gzy1": "brB",
            }
        )

        satellite_ids = self._satellite_ids(calculator.satellites)
        fixed_neighbors = self._build_fixed_neighbors(calculator.satellites, strategy)
        candidate_keys = {
            self._link_key(src, dst)
            for src, neighbors in fixed_neighbors.items()
            for dst in neighbors
        }
        satellite_order = sorted(fixed_neighbors, key=lambda idx: satellite_ids[idx])
        satellite_rows = {
            satellite_idx: row_index
            for row_index, satellite_idx in enumerate(satellite_order)
        }
        # A 60x20, 6000-slice export needs about 110 MiB instead of millions
        # of Python strings. NaN represents a down link.
        histories = np.full(
            (len(satellite_order), time_slices, 4),
            np.nan,
            dtype=np.float32,
        )

        failure_model = RandomLinkFailureModel(
            enabled=random_failure_enabled,
            failure_probability=failure_probability,
            random_seed=random_seed,
        )
        step_seconds = duration_sec / time_slices

        for time_index in range(time_slices):
            calculator.propagate(current_time)
            _isl, active_links = strategy.compute_links(calculator.satellites)
            active_latency = self._active_latency_map(active_links, calculator.satellites)
            down_by_random = failure_model.step(candidate_keys, set(active_latency))

            for sat_idx, neighbors in fixed_neighbors.items():
                row_index = satellite_rows[sat_idx]
                for neighbor_slot, neighbor_idx in enumerate(neighbors):
                    key = self._link_key(sat_idx, neighbor_idx)
                    if key not in down_by_random and key in active_latency:
                        histories[row_index, time_index, neighbor_slot] = active_latency[key]

            current_time += timedelta(seconds=step_seconds)
            if progress_callback is not None and not progress_callback(time_index + 1, time_slices):
                raise LinkDatasetExportCancelled()

        output_dir = self._prepare_output_dir(output_dir)
        topology_name = f"{orbit_num}_{sat_per_orbit}"
        link_info_filename = f"link_info_{topology_name}.txt"
        link_info_path = os.path.join(output_dir, link_info_filename)
        link_info_content = generate_link_info(
            calculator.satellites,
            fixed_neighbors,
            satellite_ids,
            include_placement=True,
            host_ranges=normalized_host_ranges,
            bridge_by_host=bridge_by_host,
        )
        with open(link_info_path, "w", encoding="utf-8") as file:
            file.write(link_info_content)
            if link_info_content:
                file.write("\n")

        host_output_dirs = {
            host_range["name"]: os.path.join(
                output_dir,
                "hosts",
                host_range["name"],
                f"processed_data_{topology_name}",
            )
            for host_range in normalized_host_ranges
        }
        for host_dir in host_output_dirs.values():
            os.makedirs(host_dir, exist_ok=True)

        for sat_idx in satellite_order:
            path = os.path.join(output_dir, f"satellite_{satellite_ids[sat_idx]}.txt")
            content = self._satellite_file_content(
                sat_idx,
                fixed_neighbors,
                satellite_ids,
                histories[satellite_rows[sat_idx]],
            )
            self._write_text(path, content)

            host_name = host_for_satellite(
                calculator.satellites[sat_idx],
                normalized_host_ranges,
            )
            if host_name in host_output_dirs:
                host_path = os.path.join(
                    host_output_dirs[host_name],
                    f"satellite_{satellite_ids[sat_idx]}.txt",
                )
                self._write_text(host_path, content)

        directed_lines = link_info_content.splitlines()
        cross_vlan_map: Dict[str, int] = {}
        for line in directed_lines:
            parts = line.split()
            if len(parts) < 5 or parts[4] != "cross_host":
                continue
            left, right = parts[0].split("-", 1)
            canonical_id = "-".join(sorted((left, right)))
            if canonical_id not in cross_vlan_map:
                cross_vlan_map[canonical_id] = len(cross_vlan_map) + 1
        if len(cross_vlan_map) > 4094:
            raise ValueError(
                f"cross-host link count exceeds VLAN capacity: {len(cross_vlan_map)}"
            )
        cross_vlan_filename = f"cross_vlan_map_{topology_name}.json"
        cross_vlan_payload = {
            "topology": topology_name,
            "trunk_by_host": {
                "gzy0": "ens3f1",
                "gzy1": "eno2",
            },
            "vlan_by_link": cross_vlan_map,
        }
        self._write_json(
            os.path.join(output_dir, cross_vlan_filename),
            cross_vlan_payload,
        )
        for host_range in normalized_host_ranges:
            host_name = host_range["name"]
            host_root = os.path.dirname(host_output_dirs[host_name])
            local_lines = [
                line
                for line in directed_lines
                if len(line.split()) >= 4
                and line.split()[3].split("-", 1)[0] == host_name
            ]
            self._write_text(
                os.path.join(host_root, link_info_filename),
                "\n".join(local_lines) + ("\n" if local_lines else ""),
            )
            self._write_json(
                os.path.join(host_root, cross_vlan_filename),
                cross_vlan_payload,
            )
            self._write_json(
                os.path.join(host_root, "manifest.json"),
                {
                    "host": host_name,
                    "orbit_start": host_range["orbit_start"],
                    "orbit_end": host_range["orbit_end"],
                    "bridge": bridge_by_host.get(host_name, "brA"),
                    "topology": topology_name,
                    "step_duration_sec": step_seconds,
                    "time_slices": time_slices,
                    "satellite_count": sum(
                        1
                        for satellite in calculator.satellites
                        if host_for_satellite(satellite, normalized_host_ranges) == host_name
                    ),
                    "directed_link_count": len(local_lines),
                    "cross_vlan_count": len(cross_vlan_map),
                },
            )

        manifest_path = os.path.join(output_dir, "manifest.json")
        self._write_json(
            manifest_path,
            {
                "run_id": run_id,
                "topology": topology_name,
                "orbit_num": orbit_num,
                "sat_per_orbit": sat_per_orbit,
                "step_duration_sec": step_seconds,
                "time_slices": time_slices,
                    "host_ranges": list(normalized_host_ranges),
                    "bridge_by_host": bridge_by_host,
            },
        )

        return LinkDatasetExportResult(
            output_dir=output_dir,
            file_count=len(fixed_neighbors),
            time_slices=time_slices,
            host_output_dirs={
                name: os.path.dirname(path)
                for name, path in host_output_dirs.items()
            },
        )

    def _satellite_file_content(
        self,
        sat_idx: int,
        fixed_neighbors: Dict[int, List[int]],
        satellite_ids: Dict[int, str],
        history: np.ndarray,
    ) -> str:
        history_lines = []
        for time_index, values in enumerate(history):
            rendered = [
                "down" if np.isnan(value) else f"{float(value):.8f}"
                for value in values
            ]
            history_lines.append(f"{time_index} {' '.join(rendered)}")
        return (
            "Time\n"
            + " ".join(
                f"Satellite_{satellite_ids[neighbor_idx]}"
                for neighbor_idx in fixed_neighbors[sat_idx]
            )
            + "\n"
            + SEPARATOR
            + "\n"
            + "\n".join(history_lines)
            + "\n"
        )

    def _write_text(self, path: str, content: str) -> None:
        with open(path, "w", encoding="utf-8") as file:
            file.write(content)

    def _write_json(self, path: str, content: Dict[str, Any]) -> None:
        with open(path, "w", encoding="utf-8") as file:
            json.dump(content, file, ensure_ascii=False, indent=2)
            file.write("\n")

    def _validate(
        self,
        *,
        orbit_num: int,
        sat_per_orbit: int,
        time_slices: int,
        duration_sec: float,
        failure_probability: float,
        output_dir: str,
    ) -> None:
        if orbit_num < 3:
            raise ValueError("轨道面数至少为 3，才能提供独立的相邻轨道面。")
        if orbit_num > 99:
            raise ValueError("轨道面数最多为 99，以便生成两位卫星编号。")
        if sat_per_orbit < 3:
            raise ValueError(
                "每轨卫星数至少为 3，才能提供独立的同轨相邻卫星。"
            )
        if sat_per_orbit > 99:
            raise ValueError("每轨卫星数最多为 99，以便生成两位卫星编号。")
        if time_slices < 1:
            raise ValueError("时间片数量至少为 1。")
        if duration_sec <= 0:
            raise ValueError("仿真总时长必须大于 0。")
        if not 0.0 <= failure_probability <= 1.0:
            raise ValueError("失效概率必须位于 0 到 1 之间。")
        if not output_dir:
            raise ValueError("必须选择输出目录。")

    def _prepare_output_dir(self, parent_dir: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_dir = os.path.join(parent_dir, f"LinkDataset_{timestamp}")
        output_dir = base_dir
        suffix = 1
        while os.path.exists(output_dir):
            suffix += 1
            output_dir = f"{base_dir}_{suffix}"

        os.makedirs(output_dir, exist_ok=False)
        return output_dir

    def _satellite_ids(self, satellites: List[Any]) -> Dict[int, str]:
        return {
            idx: f"1{sat.plane_idx + 1:02d}{sat.node_idx + 1:02d}"
            for idx, sat in enumerate(satellites)
        }

    def _build_fixed_neighbors(self, satellites: List[Any], strategy: Any) -> Dict[int, List[int]]:
        if not satellites:
            return {}

        plane_count = max(sat.plane_idx for sat in satellites) + 1
        node_count = max(sat.node_idx for sat in satellites) + 1
        by_slot = {
            (sat.plane_idx, sat.node_idx): idx
            for idx, sat in enumerate(satellites)
            if sat.plane_idx >= 0 and sat.node_idx >= 0
        }

        static_edges = getattr(strategy, "static_edges", None)
        if static_edges:
            return self._build_delta_neighbors(satellites, by_slot, static_edges)

        neighbors: Dict[int, List[int]] = {}
        for idx, sat in enumerate(satellites):
            plane = sat.plane_idx
            node = sat.node_idx
            neighbors[idx] = [
                by_slot[((plane - 1) % plane_count, node)],
                by_slot[((plane + 1) % plane_count, node)],
                by_slot[(plane, (node - 1) % node_count)],
                by_slot[(plane, (node + 1) % node_count)],
            ]
        return neighbors

    def _build_delta_neighbors(
        self,
        satellites: List[Any],
        by_slot: Dict[Tuple[int, int], int],
        static_edges: List[Tuple[str, int, int]],
    ) -> Dict[int, List[int]]:
        plane_count = max(sat.plane_idx for sat in satellites) + 1
        node_count = max(sat.node_idx for sat in satellites) + 1

        inter_right: Dict[int, int] = {}
        inter_left: Dict[int, int] = {}
        intra_next: Dict[int, int] = {}
        intra_prev: Dict[int, int] = {}

        for edge_type, src, tgt in static_edges:
            if edge_type == "inter":
                inter_right[src] = tgt
                inter_left[tgt] = src
            elif edge_type == "intra":
                intra_next[src] = tgt
                intra_prev[tgt] = src

        neighbors: Dict[int, List[int]] = {}
        for idx, sat in enumerate(satellites):
            plane = sat.plane_idx
            node = sat.node_idx
            neighbors[idx] = [
                inter_left.get(idx, by_slot[((plane - 1) % plane_count, node)]),
                inter_right.get(idx, by_slot[((plane + 1) % plane_count, node)]),
                intra_prev.get(idx, by_slot[(plane, (node - 1) % node_count)]),
                intra_next.get(idx, by_slot[(plane, (node + 1) % node_count)]),
            ]
        return neighbors

    def _active_latency_map(
        self,
        active_links: List[Dict[str, Any]],
        satellites: List[Any],
    ) -> Dict[LinkKey, float]:
        active_latency: Dict[LinkKey, float] = {}
        for link in active_links:
            src = int(link["src"])
            tgt = int(link["tgt"])
            active_latency[self._link_key(src, tgt)] = self._latency_ms(
                satellites[src].position,
                satellites[tgt].position,
            )
        return active_latency

    def _latency_ms(self, src_position: np.ndarray, tgt_position: np.ndarray) -> float:
        distance_km = float(np.linalg.norm(src_position - tgt_position))
        return (distance_km / LIGHT_SPEED_KM_PER_S) * 1000.0

    def _link_key(self, src: int, tgt: int) -> LinkKey:
        return (src, tgt) if src < tgt else (tgt, src)
