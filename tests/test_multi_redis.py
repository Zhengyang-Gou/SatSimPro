import unittest
from types import SimpleNamespace

from core.redis_latency import MultiRedisLatencyProvider


class _FakeProvider:
    def __init__(self, value):
        self.value = value

    def get_latest_link_metrics_many(self, links, satellites, time_slice=None):
        loss_value = (
            self.value / 100.0
            if isinstance(self.value, (int, float))
            else self.value
        )
        return {
            "delay": {
                (link["src"], link["tgt"]): self.value
                for link in links
            },
            "loss": {
                (link["src"], link["tgt"]): loss_value
                for link in links
            },
        }

    def close(self):
        pass


class MultiRedisLatencyProviderTests(unittest.TestCase):
    def test_routes_directed_links_by_source_orbit(self):
        provider = MultiRedisLatencyProvider(
            backends=[
                {"name": "gzy0", "orbit_start": 1, "orbit_end": 30},
                {"name": "gzy1", "orbit_start": 31, "orbit_end": 60},
            ],
            loss_enabled=True,
        )
        provider.providers = {
            "gzy0": _FakeProvider(10.0),
            "gzy1": _FakeProvider(20.0),
        }
        satellites = [
            SimpleNamespace(plane_idx=29),
            SimpleNamespace(plane_idx=30),
        ]
        links = [
            {"src": 0, "tgt": 1},
            {"src": 1, "tgt": 0},
        ]

        result = provider.get_latest_link_metrics_many(links, satellites, 7)

        self.assertEqual(result["delay"][(0, 1)], 10.0)
        self.assertEqual(result["delay"][(1, 0)], 20.0)
        self.assertEqual(result["loss"][(0, 1)], 0.1)
        self.assertEqual(result["loss"][(1, 0)], 0.2)

    def test_cross_host_link_falls_back_to_target_backend(self):
        provider = MultiRedisLatencyProvider(
            backends=[
                {"name": "gzy0", "orbit_start": 1, "orbit_end": 30},
                {"name": "gzy1", "orbit_start": 31, "orbit_end": 60},
            ],
            loss_enabled=True,
        )
        provider.providers = {
            "gzy0": _FakeProvider("down"),
            "gzy1": _FakeProvider(20.0),
        }
        satellites = [
            SimpleNamespace(plane_idx=29),
            SimpleNamespace(plane_idx=30),
        ]

        result = provider.get_latest_link_metrics_many(
            [{"src": 0, "tgt": 1}],
            satellites,
            7,
        )

        self.assertEqual(result["delay"][(0, 1)], 20.0)
        self.assertEqual(result["loss"][(0, 1)], 0.2)


if __name__ == "__main__":
    unittest.main()
