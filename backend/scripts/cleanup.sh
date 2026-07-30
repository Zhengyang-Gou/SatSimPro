#!/usr/bin/env bash

set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

deployment_marker="$SATNET_STATE_DIR/deployment.env"
expected_session=${SATNET_EXPECT_SESSION_ID:-}
force_cleanup=${SATNET_FORCE_CLEANUP:-0}
active_session=""

if [[ -r "$deployment_marker" ]]; then
    active_session=$(
        sed -n 's/^session_id=//p' "$deployment_marker" |
            head -n 1
    )
fi

if [[ "$force_cleanup" != "1" ]] && [[ -n "$expected_session" ]] &&
    [[ "$active_session" != "$expected_session" ]]; then
    printf 'cleanup refused: backend=%s expected_session=%s active_session=%s\n' \
        "$SATNET_BACKEND" "$expected_session" "${active_session:-none}" >&2
    exit 4
fi

receiver_bin="$SATNET_PLATFORM_ROOT/bin/recv_process_packets"
if [[ -n "$receiver_bin" ]]; then
    pkill -f "^${receiver_bin}( |$)" 2>/dev/null || true
fi

if command -v docker >/dev/null 2>&1; then
    docker ps -a --format '{{.Names}}' |
        awk \
            -v first="$SATNET_ORBIT_START" \
            -v last="$SATNET_ORBIT_END" \
            '
                /^S1[0-9][0-9][0-9][0-9]$/ {
                    orbit = substr($0, 3, 2) + 0
                    if (orbit >= first && orbit <= last) {
                        print
                    }
                }
            ' |
        xargs -r docker rm -f
fi

if command -v ovs-vsctl >/dev/null 2>&1; then
    ovs-vsctl --no-wait --if-exists del-br "$SATNET_BRIDGE"
fi

rm -f \
    "$SATNET_STATE_DIR/last_slice.json" \
    "$SATNET_STATE_DIR/current_timeslice" \
    "$deployment_marker" \
    "/tmp/satnet_${SATNET_BACKEND}/last_slice.json" \
    "/tmp/satnet_${SATNET_BACKEND}/current_timeslice" \
    "/tmp/current_timeslice"

printf 'cleanup completed: backend=%s session=%s\n' \
    "$SATNET_BACKEND" "${active_session:-untracked}"
