import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import numpy as np

from core.calculator import OrbitCalculator
from core.strategies import GridDeltaStrategy
from gui.config import build_ssh_command, env_float, env_int


class OrbitCalculatorTests(unittest.TestCase):
    def test_vectorized_propagation_updates_all_satellites(self):
        epoch = datetime(2026, 1, 1)
        calculator = OrbitCalculator()
        calculator.generate_walker(12, 3, 1, 550.0, 53.0, epoch)

        calculator.propagate(epoch + timedelta(seconds=30))

        positions = np.asarray([sat.position for sat in calculator.satellites])
        eci_positions = np.asarray([sat.position_eci for sat in calculator.satellites])
        self.assertEqual(positions.shape, (12, 3))
        self.assertTrue(np.isfinite(positions).all())
        np.testing.assert_allclose(
            np.linalg.norm(eci_positions, axis=1),
            np.full(12, 6371.0 + 550.0),
            rtol=1e-12,
        )

    def test_grid_strategy_reuses_sorted_static_edges(self):
        epoch = datetime(2026, 1, 1)
        calculator = OrbitCalculator()
        calculator.generate_walker(9, 3, 0, 550.0, 53.0, epoch)
        calculator.propagate(epoch)
        strategy = GridDeltaStrategy()

        first_isl, first_links = strategy.compute_links(calculator.satellites)
        cached_pairs = strategy._static_edge_pairs
        second_isl, second_links = strategy.compute_links(calculator.satellites)

        self.assertIs(strategy._static_edge_pairs, cached_pairs)
        np.testing.assert_array_equal(first_isl, second_isl)
        self.assertEqual(first_links, second_links)


class ConfigTests(unittest.TestCase):
    def test_numeric_environment_values_are_clamped(self):
        with patch.dict(os.environ, {"TEST_INT": "0", "TEST_FLOAT": "-1"}):
            self.assertEqual(env_int("TEST_INT", 2, minimum=1), 1)
            self.assertEqual(env_float("TEST_FLOAT", 1.0, minimum=0.1), 0.1)

    def test_ssh_command_does_not_require_an_ssh_alias(self):
        command = build_ssh_command("true", ssh_host_alias="")
        self.assertIn("BatchMode=yes", command)
        self.assertIn("ConnectTimeout=10", command)
        self.assertIn("-p", command)
        self.assertTrue(command[-2].endswith("@121.48.163.223"))
        self.assertEqual(command[-1], "true")


if __name__ == "__main__":
    unittest.main()
