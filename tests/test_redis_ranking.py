import unittest

from gui.trend_panel import ranked_metric_data
from gui.topology_registry import TopologyRegistry


class RedisRankingTests(unittest.TestCase):
    def test_returns_top_five_and_average_of_all_valid_values(self):
        records = [
            {"id": f"link-{index}", "redis_loss_pct": value}
            for index, value in enumerate((1, 8, 3, 6, 2, 10, 4), start=1)
        ]

        result = ranked_metric_data(records, "redis_loss_pct")

        self.assertEqual(
            [label for label, _value in result],
            ["link-6", "link-2", "link-4", "link-7", "link-3", "平均"],
        )
        self.assertAlmostEqual(result[-1][1], 34 / 7)

    def test_ignores_down_and_invalid_values(self):
        records = [
            {"id": "valid", "redis_delay_ms": 12.5},
            {"id": "down", "redis_delay_ms": "down"},
            {"id": "missing"},
            {"id": "invalid", "redis_delay_ms": "not-a-number"},
        ]

        self.assertEqual(
            ranked_metric_data(records, "redis_delay_ms"),
            [("valid", 12.5), ("平均", 12.5)],
        )

    def test_registry_retains_raw_redis_delay_for_the_ranking(self):
        registry = TopologyRegistry()
        registry.link_registry[(0, 1)] = {
            "id": "1-2",
            "src": 0,
            "tgt": 1,
            "latency": 5.0,
            "redis_delay_ms": "down",
            "redis_delay_ratio_pct": "down",
            "_redis_delay_ratio_target": "down",
        }
        registry.active_link_keys = {(0, 1)}

        registry.apply_redis_delay({(0, 1): 7.5})

        record = registry.link_registry[(0, 1)]
        self.assertEqual(record["redis_delay_ms"], 7.5)
        self.assertEqual(record["redis_delay_ratio_pct"], 150.0)


if __name__ == "__main__":
    unittest.main()
