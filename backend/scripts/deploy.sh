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
        bash "$SCRIPT_DIR/apply_compat_patches.sh"
        export SATNET_BACKEND_ROOT SATNET_DKY_ROOT SATNET_LYH_ROOT
        export SATNET_PLATFORM_ROOT SATNET_DATA_ROOT SATNET_STATE_DIR SATNET_LOG_DIR
        export SATNET_BASE="$SATNET_PLATFORM_ROOT"
        export SATNET_BRIDGE
        export SATNET_TRUNK_PORT="$SATNET_TRUNK_INTERFACE"
        bash "$target" "$@"

        printf '0\n' >"$SATNET_STATE_DIR/current_timeslice"
        session_id=${SATNET_SESSION_ID:-"manual-$(date +%s)"}
        if [[ ! "$session_id" =~ ^[A-Za-z0-9._-]+$ ]]; then
            echo "invalid SATNET_SESSION_ID: $session_id" >&2
            exit 2
        fi
        marker="$SATNET_STATE_DIR/deployment.env"
        marker_tmp="${marker}.tmp.$$"
        {
            printf 'session_id=%s\n' "$session_id"
            printf 'backend=%s\n' "$SATNET_BACKEND"
            printf 'deployed_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        } >"$marker_tmp"
        chmod 644 "$marker_tmp"
        mv -f "$marker_tmp" "$marker"
        printf 'SATNET_DEPLOYED_SESSION=%s\n' "$session_id"
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
