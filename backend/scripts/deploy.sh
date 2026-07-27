#!/usr/bin/env bash

set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

case "${SATNET_CONTROL_MODE:-legacy}" in
    legacy)
        target="$SATNET_PLATFORM_ROOT/scripts/deploy.sh"
        require_file "$target"
        # The imported D-KY scripts use two different log locations:
        # deploy_all.sh uses scripts/logs, while build_xdp.sh writes to logs.
        # Create both here so a clean backend install can build XDP programs.
        mkdir -p \
            "$SATNET_DATA_ROOT" \
            "$SATNET_STATE_DIR" \
            "$SATNET_LOG_DIR" \
            "$SATNET_DKY_ROOT/logs" \
            "$SATNET_DKY_ROOT/scripts/logs"
        # The platform deploy recreates the OVS bridge. Its legacy cleanup only
        # removes /tmp state, while the stable integration stores state under
        # runtime/state. Remove that persistent snapshot as well so slice 0 is
        # applied as a full baseline instead of an empty incremental update.
        rm -f \
            "$SATNET_STATE_DIR/last_slice.json" \
            "$SATNET_STATE_DIR/current_timeslice"
        export SATNET_BACKEND_ROOT SATNET_DKY_ROOT SATNET_LYH_ROOT
        export SATNET_PLATFORM_ROOT SATNET_DATA_ROOT SATNET_STATE_DIR SATNET_LOG_DIR
        export SATNET_BASE="$SATNET_PLATFORM_ROOT"
        export SATNET_BRIDGE
        export SATNET_TRUNK_PORT="$SATNET_TRUNK_INTERFACE"
        exec bash "$target" "$@"
        ;;
    lyh)
        echo "LYH adapter is not enabled yet; refusing to mix controllers" >&2
        exit 3
        ;;
    *)
        echo "unsupported SATNET_CONTROL_MODE: $SATNET_CONTROL_MODE" >&2
        exit 2
        ;;
esac
