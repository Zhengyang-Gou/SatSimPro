#!/usr/bin/env bash

set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

case "${SATNET_CONTROL_MODE:-legacy}" in
    legacy)
        target="$SATNET_PLATFORM_ROOT/scripts/measure_slice.sh"
        require_file "$target"
        mkdir -p "$SATNET_DATA_ROOT" "$SATNET_STATE_DIR" "$SATNET_LOG_DIR"
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
