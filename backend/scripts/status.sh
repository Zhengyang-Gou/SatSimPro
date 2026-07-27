#!/usr/bin/env bash

set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

printf 'backend=%s\n' "$SATNET_BACKEND"
printf 'control_mode=%s\n' "$SATNET_CONTROL_MODE"
printf 'orbits=%s-%s\n' "$SATNET_ORBIT_START" "$SATNET_ORBIT_END"
printf 'dky_source=%s\n' "$SATNET_DKY_ROOT"
printf 'lyh_source=%s\n' "$SATNET_LYH_ROOT"
printf 'platform_source=%s\n' "$SATNET_PLATFORM_ROOT"
printf 'data_root=%s\n' "$SATNET_DATA_ROOT"

test -x "$SATNET_DKY_ROOT/scripts/deploy_all.sh"
test -f "$SATNET_LYH_ROOT/scripts/run_all_lyh.sh"
test -f "$SATNET_PLATFORM_ROOT/scripts/deploy.sh"
test -f "$SATNET_PLATFORM_ROOT/scripts/measure_slice.sh"
test -f "$SATNET_DATA_ROOT/link_info_60_20.txt"
test -f "$SATNET_DATA_ROOT/cross_vlan_map_60_20.json"
test -d "$SATNET_DATA_ROOT/processed_data_60_20"

if command -v ovs-vsctl >/dev/null 2>&1; then
    ovs-vsctl br-exists "$SATNET_BRIDGE" 2>/dev/null &&
        printf 'bridge=%s:up\n' "$SATNET_BRIDGE" ||
        printf 'bridge=%s:absent\n' "$SATNET_BRIDGE"
fi
