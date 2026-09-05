"""Topology registry: stable full-link table plus per-frame link state updates."""

from typing import Any, Dict, List, Set

from core.strategies import GridDeltaStrategy
from core.metrics import MISSING, INVALID, ERROR, valid_metric

from .link_state import (
    LinkKey,
    LinkRecord,
    directed_link_key,
    is_down,
    link_key,
    remote_host_name,
    remote_sat_id,
)
from .theme import DOWN


class TopologyRegistry:
    REDIS_SMOOTHING = 0.22

    """
    Keeps a stable table of theoretically possible links.

    The simulation loop only updates each link's live state. It does not add/remove
    table rows every frame, so pagination and selection remain stable.
    """

    def __init__(self, host_ranges=None):
        self.link_registry: Dict[LinkKey, LinkRecord] = {}
        self.all_links_data: List[LinkRecord] = []
        self.active_link_keys: Set[LinkKey] = set()
        self.active_count = 0
        self.is_locked = False
        self.host_ranges = host_ranges

    def reset(self, strategy: Any) -> None:
        self.link_registry.clear()
        self.all_links_data.clear()
        self.active_link_keys.clear()
        self.active_count = 0
        self.is_locked = False

        if isinstance(strategy, GridDeltaStrategy):
            strategy.static_edges = None
            strategy._static_edge_pairs = None

    def build_if_needed(self, strategy: Any, satellites: List[Any]) -> None:
        if self.is_locked:
            return
        self.build(strategy, satellites)
        self.is_locked = True

    def build(self, strategy: Any, satellites: List[Any]) -> None:
        """Build the complete theoretical topology for the current strategy."""
        self.link_registry.clear()
        self.active_link_keys.clear()
        self.active_count = 0

        if not satellites:
            self.all_links_data = []
            return

        self._build_delta_registry(strategy, satellites)

        self.all_links_data = sorted(
            self.link_registry.values(),
            key=lambda x: (x["src_id"], x["neighbor_order"], x["tgt_id"]),
        )

    def _build_delta_registry(self, strategy: GridDeltaStrategy, satellites: List[Any]) -> None:
        if strategy.static_edges is None:
            strategy.compute_links(satellites)

        if not strategy.static_edges:
            return

        undirected_edges = set()
        for _edge_type, src, tgt in strategy.static_edges:
            undirected_edges.add(link_key(src, tgt))

        neighbors_by_src: Dict[int, List[int]] = {}
        for src, tgt in sorted(undirected_edges):
            neighbors_by_src.setdefault(src, []).append(tgt)
            neighbors_by_src.setdefault(tgt, []).append(src)

        neighbor_order: Dict[LinkKey, int] = {}
        for src, neighbors in neighbors_by_src.items():
            ordered_neighbors = sorted(neighbors, key=lambda idx: remote_sat_id(satellites[idx]))
            for order, tgt in enumerate(ordered_neighbors):
                neighbor_order[directed_link_key(src, tgt)] = order

        for src, tgt in sorted(undirected_edges):
            self.link_registry[directed_link_key(src, tgt)] = self._new_link_record(
                src,
                tgt,
                satellites,
                neighbor_order.get(directed_link_key(src, tgt), 0),
            )
            self.link_registry[directed_link_key(tgt, src)] = self._new_link_record(
                tgt,
                src,
                satellites,
                neighbor_order.get(directed_link_key(tgt, src), 0),
            )

    def _new_link_record(
        self,
        src: int,
        tgt: int,
        satellites: List[Any],
        neighbor_order: int,
    ) -> LinkRecord:
        src_id = remote_sat_id(satellites[src])
        tgt_id = remote_sat_id(satellites[tgt])
        src_host = remote_host_name(satellites[src], self.host_ranges)
        tgt_host = remote_host_name(satellites[tgt], self.host_ranges)
        return {
            "id": f"{src_id}-{tgt_id}",
            "src": src,
            "tgt": tgt,
            "src_id": src_id,
            "tgt_id": tgt_id,
            "src_name": str(src_id),
            "tgt_name": str(tgt_id),
            "src_host": src_host,
            "tgt_host": tgt_host,
            "scope": "local" if src_host == tgt_host else "cross_host",
            "neighbor_order": neighbor_order,
            "latency": DOWN,
            "redis_delay_ms": MISSING,
            "redis_delay_ratio_pct": MISSING,
            "redis_loss_pct": MISSING,
            "_redis_delay_ratio_target": MISSING,
            "_redis_loss_target": MISSING,
        }

    def apply_active_links(self, active_links: List[LinkRecord]) -> None:
        current_active_keys = set()

        for active in active_links:
            for src, tgt in ((active["src"], active["tgt"]), (active["tgt"], active["src"])):
                key = directed_link_key(src, tgt)
                record = self.link_registry.get(key)
                if record is None:
                    continue

                record["latency"] = active["latency"]
                self._advance_redis_display(record)
                current_active_keys.add(key)

        for key in self.active_link_keys - current_active_keys:
            record = self.link_registry.get(key)
            if record is None:
                continue

            record["latency"] = DOWN
            record["redis_delay_ms"] = DOWN
            record["redis_delay_ratio_pct"] = DOWN
            record["redis_loss_pct"] = DOWN
            record["_redis_delay_ratio_target"] = DOWN
            record["_redis_loss_target"] = DOWN

        self.active_link_keys = current_active_keys
        self.active_count = len(current_active_keys)

    def _advance_redis_display(self, record: LinkRecord) -> None:
        record["redis_delay_ratio_pct"] = self._smooth_metric(
            record.get("redis_delay_ratio_pct", DOWN),
            record.get("_redis_delay_ratio_target", DOWN),
        )
        record["redis_loss_pct"] = self._smooth_metric(
            record.get("redis_loss_pct", DOWN),
            record.get("_redis_loss_target", DOWN),
        )

    def active_for_redis(self) -> List[LinkRecord]:
        return [
            {"src": record["src"], "tgt": record["tgt"]}
            for key in sorted(
                self.active_link_keys,
                key=lambda item: (
                    self.link_registry[item]["src_id"],
                    self.link_registry[item]["neighbor_order"],
                    self.link_registry[item]["tgt_id"],
                ),
            )
            if (record := self.link_registry.get(key)) is not None
            and not is_down(record.get("latency"))
        ]

    def apply_redis_delay(self, redis_delay_map: Dict[LinkKey, Any]) -> None:
        for key in self.active_link_keys:
            record = self.link_registry.get(key)
            if record is None:
                continue

            if is_down(record.get("latency", DOWN)):
                record["redis_delay_ms"] = DOWN
                record["redis_delay_ratio_pct"] = DOWN
                record["redis_loss_pct"] = DOWN
                continue

            measured_delay = valid_metric(redis_delay_map.get((record["src"], record["tgt"]), MISSING))
            if isinstance(measured_delay, str):
                target = measured_delay
            else:
                latency = valid_metric(record["latency"])
                target = (round(measured_delay / latency * 100.0, 4)
                          if isinstance(latency, float) and latency > 0 else INVALID)
                measured_delay = round(measured_delay, 4)
            record["redis_delay_ms"] = measured_delay
            record["_redis_delay_ratio_target"] = target
            record["redis_delay_ratio_pct"] = self._smooth_metric(
                record.get("redis_delay_ratio_pct", DOWN),
                target,
            )

    def apply_redis_loss(self, redis_loss_map: Dict[LinkKey, Any]) -> None:
        for key in self.active_link_keys:
            record = self.link_registry.get(key)
            if record is None:
                continue

            if is_down(record.get("latency", DOWN)):
                record["redis_loss_pct"] = DOWN
                continue

            target = valid_metric(redis_loss_map.get((record["src"], record["tgt"]), MISSING), maximum=100.0)
            record["_redis_loss_target"] = target
            record["redis_loss_pct"] = self._smooth_metric(record.get("redis_loss_pct", DOWN), target)

    def _smooth_metric(self, current: Any, target: Any) -> Any:
        target = valid_metric(target)
        current = valid_metric(current)
        if isinstance(target, str):
            return target
        if isinstance(current, str):
            return target
        current_f, target_f = current, target

        value = current_f + (target_f - current_f) * self.REDIS_SMOOTHING
        return round(value, 4)

    def mark_redis_down(self, status=ERROR) -> None:
        for record in self.link_registry.values():
            record["redis_delay_ms"] = status
            record["redis_delay_ratio_pct"] = status
            record["redis_loss_pct"] = status
            record["_redis_delay_ratio_target"] = status
            record["_redis_loss_target"] = status
