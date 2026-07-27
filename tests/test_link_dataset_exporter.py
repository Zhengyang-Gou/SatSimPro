import os
import json
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
                "link_info_3_3.txt",
            )
            self.assertTrue(os.path.isfile(link_info_path))

            with open(link_info_path, encoding="utf-8") as file:
                lines = file.read().splitlines()

            self.assertEqual(len(lines), 3 * 3 * 4)
            self.assertIn(
                "10101-10102 "
                "S10101_2-S10102_1 "
                "brB10101_2-brB10102_1 "
                "gzy0-gzy0 local",
                lines,
            )
            self.assertIn(
                "10102-10101 "
                "S10102_1-S10101_2 "
                "brB10102_1-brB10101_2 "
                "gzy0-gzy0 local",
                lines,
            )
            self.assertTrue(os.path.isdir(result.host_output_dirs["gzy0"]))
            self.assertTrue(
                os.path.isfile(
                    os.path.join(
                        result.host_output_dirs["gzy0"],
                        "processed_data_3_3",
                        "satellite_10101.txt",
                    )
                )
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

    def test_60x20_export_is_split_into_two_600_satellite_packages(self):
        with tempfile.TemporaryDirectory() as parent_dir:
            result = LinkDatasetExporter().export(
                orbit_num=60,
                sat_per_orbit=20,
                time_slices=1,
                duration_sec=10.0,
                output_dir=parent_dir,
                start_time=datetime(2026, 1, 1),
            )

            with open(
                os.path.join(result.output_dir, "link_info_60_20.txt"),
                encoding="utf-8",
            ) as file:
                link_lines = file.read().splitlines()
            self.assertEqual(result.file_count, 1200)
            self.assertEqual(len(link_lines), 4800)
            self.assertEqual(sum(line.endswith("cross_host") for line in link_lines), 80)
            with open(
                os.path.join(result.output_dir, "cross_vlan_map_60_20.json"),
                encoding="utf-8",
            ) as file:
                global_vlan_map = json.load(file)
            self.assertEqual(len(global_vlan_map["vlan_by_link"]), 40)
            self.assertEqual(
                sorted(global_vlan_map["vlan_by_link"].values()),
                list(range(1, 41)),
            )

            for backend_name in ("gzy0", "gzy1"):
                host_root = result.host_output_dirs[backend_name]
                data_dir = os.path.join(host_root, "processed_data_60_20")
                satellite_files = [
                    name
                    for name in os.listdir(data_dir)
                    if name.startswith("satellite_")
                ]
                self.assertEqual(len(satellite_files), 600)
                with open(
                    os.path.join(host_root, "link_info_60_20.txt"),
                    encoding="utf-8",
                ) as file:
                    self.assertEqual(len(file.read().splitlines()), 2400)
                with open(
                    os.path.join(host_root, "cross_vlan_map_60_20.json"),
                    encoding="utf-8",
                ) as file:
                    self.assertEqual(json.load(file), global_vlan_map)
                with open(
                    os.path.join(host_root, "manifest.json"),
                    encoding="utf-8",
                ) as file:
                    self.assertEqual(json.load(file)["bridge"], "brB")
