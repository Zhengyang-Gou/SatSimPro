"""Generate OVS port mappings for fixed satellite links."""

PORTS_BY_NEIGHBOR_SLOT = (4, 3, 1, 2)


def generate_link_info(satellites, fixed_neighbors, satellite_ids) -> str:
    """Return the contents of a link_info file for the supplied constellation."""
    lines = []
    emitted = set()
    port_map = _build_port_map(fixed_neighbors)
    for satellite_idx, neighbors in fixed_neighbors.items():
        satellite = satellites[satellite_idx]
        sat_id = satellite_ids[satellite_idx]
        for neighbor_idx in neighbors:
            neighbor = satellites[neighbor_idx]
            neighbor_id = satellite_ids[neighbor_idx]
            _append_link(
                lines,
                emitted,
                port_map,
                satellite_idx,
                neighbor_idx,
                satellite,
                neighbor,
                sat_id,
                neighbor_id,
            )
            _append_link(
                lines,
                emitted,
                port_map,
                neighbor_idx,
                satellite_idx,
                neighbor,
                satellite,
                neighbor_id,
                sat_id,
            )

    return "\n".join(lines)


def _build_port_map(fixed_neighbors):
    port_map = {}
    for satellite_idx, neighbors in fixed_neighbors.items():
        if len(neighbors) != len(PORTS_BY_NEIGHBOR_SLOT):
            continue

        for slot, neighbor_idx in enumerate(neighbors):
            port_map[(satellite_idx, neighbor_idx)] = PORTS_BY_NEIGHBOR_SLOT[slot]
    return port_map


def _append_link(
    lines,
    emitted,
    port_map,
    satellite_idx,
    neighbor_idx,
    satellite,
    neighbor,
    sat_id,
    neighbor_id,
):
    key = (sat_id, neighbor_id)
    if key in emitted:
        return

    emitted.add(key)
    self_port, neighbor_port = _ports_for_link(
        port_map,
        satellite_idx,
        neighbor_idx,
        satellite,
        neighbor,
    )
    lines.append(
        f"{sat_id}-{neighbor_id} "
        f"S{sat_id}_{self_port}-S{neighbor_id}_{neighbor_port} "
        f"brA{sat_id}_{self_port}-brA{neighbor_id}_{neighbor_port}"
    )


def _ports_for_link(port_map, satellite_idx, neighbor_idx, satellite, neighbor):
    mapped_self_port = port_map.get((satellite_idx, neighbor_idx))
    mapped_neighbor_port = port_map.get((neighbor_idx, satellite_idx))
    if mapped_self_port is not None and mapped_neighbor_port is not None:
        return mapped_self_port, mapped_neighbor_port

    fallback_self_port, fallback_neighbor_port = _topology_ports_for_link(satellite, neighbor)
    return (
        mapped_self_port if mapped_self_port is not None else fallback_self_port,
        mapped_neighbor_port if mapped_neighbor_port is not None else fallback_neighbor_port,
    )


def _topology_ports_for_link(satellite, neighbor):
    if satellite.plane_idx == neighbor.plane_idx:
        if satellite.node_idx < neighbor.node_idx:
            return 2, 1
        return 1, 2

    if satellite.plane_idx < neighbor.plane_idx:
        return 3, 4
    return 4, 3
