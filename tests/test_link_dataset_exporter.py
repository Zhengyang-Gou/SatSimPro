import os
import re
import tempfile
import unittest
from datetime import datetime

from core.link_dataset_exporter import LinkDatasetExporter


class LinkDatasetExporterTests(unittest.TestCase):
    def test_export_writes_link_info_mapping_file(self):
        with tempfile.TemporaryDirectory() as parent_dir:
            result = LinkDatasetExporter().export(
                orbit_num=3,
                sat_per_orbit=3,
                time_slices=1,
                duration_sec=1.0,
                output_dir=parent_dir,
                start_time=datetime(2026, 1, 1),
            )

            link_info_path = os.path.join(
                result.output_dir,
                "link_info_15_35.txt",
            )
            self.assertTrue(os.path.isfile(link_info_path))

            with open(link_info_path, encoding="utf-8") as file:
                lines = file.read().splitlines()

            self.assertEqual(len(lines), 3 * 3 * 4)
            self.assertIn(
                "10101-10102 "
                "S10101_2-S10102_1 "
                "brA10101_2-brA10102_1",
                lines,
            )
            self.assertIn(
                "10102-10101 "
                "S10102_1-S10101_2 "
                "brA10102_1-brA10101_2",
                lines,
            )

            endpoint_neighbors = {}
            for line in lines:
                match = re.search(r"S(\d+)_(\d+)-S(\d+)_(\d+)", line)
                self.assertIsNotNone(match)

                left_sat, left_port, right_sat, right_port = match.groups()
                left_endpoint = (left_sat, left_port)
                right_endpoint = (right_sat, right_port)
                endpoint_neighbors.setdefault(left_endpoint, set()).add(right_endpoint)
                endpoint_neighbors.setdefault(right_endpoint, set()).add(left_endpoint)

            reused_ports = {
                endpoint: neighbors
                for endpoint, neighbors in endpoint_neighbors.items()
                if len(neighbors) > 1
            }
            self.assertEqual(reused_ports, {})
