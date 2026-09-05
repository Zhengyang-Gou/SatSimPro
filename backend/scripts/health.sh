#!/usr/bin/env bash

set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

nodes_per_orbit=${SATNET_NODES_PER_ORBIT:-20}
expected_containers=$(( (SATNET_ORBIT_END - SATNET_ORBIT_START + 1) * nodes_per_orbit ))
deployment_marker="$SATNET_STATE_DIR/deployment.env"
session_id=""
reasons=()

if [[ -r "$deployment_marker" ]]; then
    session_id=$(
        sed -n 's/^session_id=//p' "$deployment_marker" |
            head -n 1
    )
fi

if ! command -v docker >/dev/null 2>&1; then
    reasons+=("docker-unavailable")
    container_count=0
else
    container_names=$(docker ps --format '{{.Names}}' 2>/dev/null) || {
        container_names=""
        reasons+=("docker-unreachable")
    }
    container_count=$(
        awk \
            -v first="$SATNET_ORBIT_START" \
            -v last="$SATNET_ORBIT_END" \
            '
                /^S1[0-9][0-9][0-9][0-9]$/ {
                    orbit = substr($0, 3, 2) + 0
                    if (orbit >= first && orbit <= last) {
                        count++
                    }
                }
                END { print count + 0 }
            ' <<<"$container_names"
    )
    if (( container_count != expected_containers )); then
        reasons+=("containers=${container_count}/${expected_containers}")
    fi
fi

if ! command -v ovs-vsctl >/dev/null 2>&1; then
    reasons+=("ovs-unavailable")
elif ! ovs-vsctl br-exists "$SATNET_BRIDGE" >/dev/null 2>&1; then
    reasons+=("bridge-absent")
fi

receiver_bin="$SATNET_PLATFORM_ROOT/bin/recv_process_packets"
if [[ -x "$receiver_bin" ]] && ! pgrep -f "^${receiver_bin}( |$)" >/dev/null 2>&1; then
    reasons+=("receiver-stopped")
fi

if [[ ! -s "$SATNET_STATE_DIR/current_timeslice" ]] &&
    [[ ! -s "/tmp/satnet_${SATNET_BACKEND}/current_timeslice" ]]; then
    reasons+=("timeslice-state-absent")
fi

# Report only the manifest from the active controller data directory.
# A missing legacy manifest does not hide resources from lifecycle cleanup;
# the GUI refuses remote playback until versioned metadata is available.
manifest_path="$SATNET_DATA_ROOT/manifest.json"
if [[ -r "$manifest_path" ]]; then
    if ! python3 - "$manifest_path" <<'PYMANIFEST'
import json
import sys
try:
    with open(sys.argv[1], encoding="utf-8") as source:
        manifest = json.load(source)
    print("SATNET_MANIFEST=" + json.dumps(manifest, separators=(",", ":"), allow_nan=False))
except (OSError, ValueError) as exc:
    print("invalid dataset manifest: " + str(exc), file=sys.stderr)
    sys.exit(1)
PYMANIFEST
    then
        reasons+=("manifest-invalid")
    fi
fi

printf 'SATNET_BACKEND=%s\n' "$SATNET_BACKEND"
printf 'SATNET_SESSION_ID=%s\n' "$session_id"
printf 'SATNET_CONTAINER_COUNT=%s\n' "$container_count"
printf 'SATNET_EXPECTED_CONTAINERS=%s\n' "$expected_containers"

if (( ${#reasons[@]} == 0 )); then
    printf 'SATNET_HEALTH=deployed\n'
    exit 0
fi

printf 'SATNET_HEALTH=not-deployed\n'
printf 'SATNET_REASONS=%s\n' "$(IFS=,; echo "${reasons[*]}")"
exit 3
