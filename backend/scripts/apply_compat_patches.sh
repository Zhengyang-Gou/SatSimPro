#!/usr/bin/env bash

set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

target="$SATNET_PLATFORM_ROOT/scripts/docker_ovs_setup_fast.py"
require_file "$target"

apply_patch_once() {
    local name=$1
    local marker=$2
    local patch_file=$3

    require_file "$patch_file"
    if grep -Fq -- "$marker" "$target"; then
        echo "compat_patch=$name:already-applied"
        return
    fi

    patch --batch --forward -d "$SATNET_PLATFORM_ROOT" -p1 < "$patch_file"
    if ! grep -Fq -- "$marker" "$target"; then
        echo "compatibility patch $name did not update $target" >&2
        exit 4
    fi
    echo "compat_patch=$name:applied"
}

apply_patch_once \
    "container-network-none" \
    "--network none" \
    "$SATNET_BACKEND_ROOT/patches/platform/0001-container-network-none.patch"
apply_patch_once \
    "veth-fail-fast" \
    "validate_host_interfaces" \
    "$SATNET_BACKEND_ROOT/patches/platform/0002-veth-fail-fast.patch"

if awk '
    previous == "def main():" &&
        $0 == "def validate_host_interfaces(expected_ports):" { found=1 }
    { previous=$0 }
    END { exit !found }
' "$target"; then
    indent_patch="$SATNET_BACKEND_ROOT/patches/platform/0003-veth-validation-indent.patch"
    require_file "$indent_patch"
    patch --batch --forward -d "$SATNET_PLATFORM_ROOT" -p1 < "$indent_patch"
    echo "compat_patch=veth-validation-indent:applied"
else
    echo "compat_patch=veth-validation-indent:not-needed"
fi

python3 -m py_compile "$target"
echo "compat_patch=python-syntax:ok"
