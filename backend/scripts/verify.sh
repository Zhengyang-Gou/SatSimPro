#!/usr/bin/env bash

set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

bash "$SCRIPT_DIR/status.sh"

# Syntax-check stable entry points without performing deployment.
bash -n "$SCRIPT_DIR/_common.sh"
bash -n "$SCRIPT_DIR/apply_compat_patches.sh"
bash -n "$SCRIPT_DIR/deploy.sh"
bash -n "$SCRIPT_DIR/health.sh"
bash -n "$SCRIPT_DIR/cleanup.sh"
bash -n "$SCRIPT_DIR/measure_slice.sh"
bash -n "$SCRIPT_DIR/status.sh"

old_references=$(
    grep -RIlE '/home/(s223|test)/(dky|yzy|lyh|sat_deploy)' \
        "$SATNET_DKY_ROOT" \
        "$SATNET_LYH_ROOT" \
        "$SATNET_PLATFORM_ROOT" \
        --include='*.sh' --include='*.py' --include='*.c' 2>/dev/null || true
)
if [[ -n "$old_references" ]]; then
    echo "old source references remain:" >&2
    printf '%s\n' "$old_references" >&2
    exit 4
fi

printf 'stable_entrypoints=ok\n'
