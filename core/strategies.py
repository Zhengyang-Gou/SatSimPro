import numpy as np

class Strategy:
    def compute_links(self, satellites):
        raise NotImplementedError

    def _format_edges(self, edges, satellites, *, presorted=False):
        link_stats = []

        if edges is None or len(edges) == 0:
            return np.empty((0,), dtype=np.int64), link_stats

        edge_arr = np.asarray(
            edges if presorted else sorted(edges), dtype=np.int64
        ).reshape((-1, 2))
        u_list = edge_arr[:, 0]
        v_list = edge_arr[:, 1]

        isl_arr = np.empty(edge_arr.size + len(edge_arr), dtype=np.int64)
        isl_arr[0::3] = 2
        isl_arr[1::3] = u_list
        isl_arr[2::3] = v_list

        positions = np.asarray([s.position for s in satellites], dtype=np.float64)
        dists = np.linalg.norm(positions[u_list] - positions[v_list], axis=1)
        latencies = (dists / 299792.458) * 1000.0

        for i, (src, tgt) in enumerate(edge_arr):
            src = int(src)
            tgt = int(tgt)
            link_stats.append({
                'id': i + 1,
                'src': src,
                'tgt': tgt,
                'src_name': satellites[src].name,
                'tgt_name': satellites[tgt].name,
                'latency': round(float(latencies[i]), 4),
                'latency_ms_raw': float(latencies[i])
            })

        return isl_arr, link_stats

class GridDeltaStrategy(Strategy):
    def __init__(self, latitude_fuse_enabled=False, latitude_threshold=70.0):
        self.static_edges = None
        self._static_edge_pairs = None
        self.latitude_fuse_enabled = latitude_fuse_enabled
        self.latitude_threshold = latitude_threshold
        
    def compute_links(self, satellites):
        if not satellites:
            return np.empty((0,), dtype=np.int64), []
        if self.static_edges is None:
            self.static_edges = []
            P = max(s.plane_idx for s in satellites) + 1
            S = max(s.node_idx for s in satellites) + 1
            def get_idx(plane, node):
                return (plane % P) * S + (node % S)
            for p in range(P):
                next_plane_positions = np.asarray([
                    satellites[get_idx(p + 1, ns)].position_eci
                    for ns in range(S)
                ])
                current_plane_positions = np.asarray([
                    satellites[get_idx(p, s)].position_eci
                    for s in range(S)
                ])
                shift_costs = []
                for shift in range(S):
                    shifted_positions = np.roll(next_plane_positions, -shift, axis=0)
                    dists = np.linalg.norm(current_plane_positions - shifted_positions, axis=1)
                    shift_costs.append(float(np.sum(dists)))
                best_shift = int(np.argmin(shift_costs))

                for s in range(S):
                    u_idx = get_idx(p, s)
                    self.static_edges.append(('intra', u_idx, get_idx(p, s + 1)))
                    self.static_edges.append(('inter', u_idx, get_idx(p + 1, s + best_shift)))

            unique_edges = {
                (u, v) if u < v else (v, u)
                for _edge_type, u, v in self.static_edges
            }
            self._static_edge_pairs = np.asarray(sorted(unique_edges), dtype=np.int64).reshape((-1, 2))

        if not self.latitude_fuse_enabled:
            return self._format_edges(self._static_edge_pairs, satellites, presorted=True)

        fused_inter_edges = {
            (u, v) if u < v else (v, u)
            for edge_type, u, v in self.static_edges
            if edge_type == 'inter' and self._is_latitude_fused(u, v, satellites)
        }
        active_edges = [
            tuple(edge)
            for edge in self._static_edge_pairs
            if tuple(edge) not in fused_inter_edges
        ]
        return self._format_edges(active_edges, satellites, presorted=True)

    def _is_latitude_fused(self, u, v, satellites):
        if not self.latitude_fuse_enabled:
            return False
        return (
            abs(self._geocentric_latitude(satellites[u].position)) >= self.latitude_threshold
            or abs(self._geocentric_latitude(satellites[v].position)) >= self.latitude_threshold
        )

    def _geocentric_latitude(self, position):
        norm = np.linalg.norm(position)
        if norm <= 0:
            return 0.0
        return float(np.degrees(np.arcsin(position[2] / norm)))
