import unittest
from types import SimpleNamespace

from link_info import generate_link_info


class GenerateLinkInfoTests(unittest.TestCase):
    def test_generates_all_neighbor_directions_with_topology_based_ports(self):
        satellites = [
            SimpleNamespace(plane_idx=0, node_idx=0),
            SimpleNamespace(plane_idx=1, node_idx=0),
            SimpleNamespace(plane_idx=0, node_idx=1),
            SimpleNamespace(plane_idx=2, node_idx=0),
            SimpleNamespace(plane_idx=0, node_idx=2),
        ]
        fixed_neighbors = {
            0: [2, 4, 1, 3],
            1: [0],
            2: [4, 0, 3, 1],
        }
        satellite_ids = {
            0: "10101",
            1: "10201",
            2: "10102",
            3: "10301",
            4: "10103",
        }

        result = generate_link_info(satellites, fixed_neighbors, satellite_ids)

        expected_lines = {
            "10101-10102 S10101_4-S10102_3 brA10101_4-brA10102_3",
            "10102-10101 S10102_3-S10101_4 brA10102_3-brA10101_4",
            "10101-10103 S10101_3-S10103_1 brA10101_3-brA10103_1",
            "10103-10101 S10103_1-S10101_3 brA10103_1-brA10101_3",
            "10101-10201 S10101_1-S10201_4 brA10101_1-brA10201_4",
            "10201-10101 S10201_4-S10101_1 brA10201_4-brA10101_1",
            "10101-10301 S10101_2-S10301_4 brA10101_2-brA10301_4",
            "10301-10101 S10301_4-S10101_2 brA10301_4-brA10101_2",
            "10102-10103 S10102_4-S10103_1 brA10102_4-brA10103_1",
            "10103-10102 S10103_1-S10102_4 brA10103_1-brA10102_4",
            "10102-10101 S10102_3-S10101_4 brA10102_3-brA10101_4",
            "10102-10301 S10102_1-S10301_4 brA10102_1-brA10301_4",
            "10301-10102 S10301_4-S10102_1 brA10301_4-brA10102_1",
            "10102-10201 S10102_2-S10201_4 brA10102_2-brA10201_4",
            "10201-10102 S10201_4-S10102_2 brA10201_4-brA10102_2",
        }
        result_lines = result.splitlines()
        self.assertEqual(set(result_lines), expected_lines)
        self.assertEqual(len(result_lines), len(expected_lines))

    def test_generates_reverse_direction_for_one_way_neighbors(self):
        satellites = [
            SimpleNamespace(plane_idx=0, node_idx=0),
            SimpleNamespace(plane_idx=1, node_idx=0),
        ]
        fixed_neighbors = {
            0: [1],
        }
        satellite_ids = {
            0: "10101",
            1: "10201",
        }

        result = generate_link_info(satellites, fixed_neighbors, satellite_ids)

        self.assertEqual(
            result.splitlines(),
            [
                "10101-10201 S10101_3-S10201_4 brA10101_3-brA10201_4",
                "10201-10101 S10201_4-S10101_3 brA10201_4-brA10101_3",
            ],
        )

    def test_empty_neighbors_returns_empty_content(self):
        self.assertEqual(generate_link_info([], {}, {}), "")

    def test_placement_marks_cross_host_links(self):
        satellites = [
            SimpleNamespace(plane_idx=29, node_idx=0),
            SimpleNamespace(plane_idx=30, node_idx=0),
        ]
        result = generate_link_info(
            satellites,
            {0: [1]},
            {0: "13001", 1: "13101"},
            include_placement=True,
            bridge_by_host={"gzy0": "brB", "gzy1": "brB"},
        )
        self.assertEqual(
            result.splitlines(),
            [
                "13001-13101 S13001_3-S13101_4 brB13001_3-brB13101_4 "
                "gzy0-gzy1 cross_host",
                "13101-13001 S13101_4-S13001_3 brB13101_4-brB13001_3 "
                "gzy1-gzy0 cross_host",
            ],
        )


if __name__ == "__main__":
    unittest.main()
