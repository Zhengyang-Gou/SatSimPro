from datetime import datetime
import math

import pytest

from core.calculator import OrbitCalculator
from core.metrics import ERROR, INVALID, MISSING
from core.redis_latency import RedisLatencyProvider
from core.strategies import GridDeltaStrategy
from gui.topology_registry import TopologyRegistry
from gui.trend_panel import RankingBarChart, ranked_metric_data


@pytest.fixture
def provider():
    instance = RedisLatencyProvider.__new__(RedisLatencyProvider)
    instance.loss_scale = 1.0
    return instance


@pytest.mark.parametrize("raw,expected", [
    (None, MISSING), ("", MISSING), ("123,down", "down"),
    ("123,nan", INVALID), ("123,inf", INVALID), ("123,-5", INVALID),
    ("123,garbage", INVALID), ("123,0", 0.0), ("123,12.34567", 12.3457),
])
def test_delay_validation(provider, raw, expected):
    assert provider._parse_metric_value(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("123,1.000001", INVALID), ("123,2", INVALID), ("123,-0.01", INVALID),
    ("123,nan", INVALID), ("123,0.0125", 1.25), ("123,1", 100.0),
])
def test_loss_validation(provider, raw, expected):
    assert provider._parse_loss_pct(raw) == expected


def test_zero_loss_scale_is_invalid(provider):
    provider.loss_scale = 0
    assert provider._parse_loss_pct("123,0.1") == INVALID


def test_registry_preserves_unavailable_reasons_and_recovers():
    calc = OrbitCalculator()
    epoch = datetime(2026, 1, 1)
    calc.generate_walker(9, 3, 0, 550, 53, epoch)
    calc.propagate(epoch)
    strategy = GridDeltaStrategy()
    registry = TopologyRegistry()
    registry.build_if_needed(strategy, calc.satellites)
    _, links = strategy.compute_links(calc.satellites)
    registry.apply_active_links(links)
    key = next(iter(registry.active_link_keys))
    record = registry.link_registry[key]
    for status in (MISSING, INVALID, ERROR, "down"):
        registry.apply_redis_delay({key: status})
        registry.apply_redis_loss({key: status})
        registry.apply_active_links(links)
        assert record["redis_delay_ms"] == status
        assert record["redis_delay_ratio_pct"] == status
        assert record["redis_loss_pct"] == status
    registry.apply_redis_delay({key: 10.0})
    assert math.isfinite(record["redis_delay_ratio_pct"])
    registry.mark_redis_down()
    assert record["redis_delay_ms"] == ERROR


def test_nonfinite_values_cannot_reach_ranking_axes():
    records = [{"id": str(i), "value": value} for i, value in enumerate(
        [float("nan"), float("inf"), -5, MISSING, INVALID, ERROR, 5.0])]
    assert ranked_metric_data(records, "value") == [("6", 5.0), ("平均", 5.0)]
    assert RankingBarChart._nice_axis_max(float("nan")) == 1.0
