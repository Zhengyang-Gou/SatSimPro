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

# Bridge deletion must complete before docker_ovs_setup_fast.py starts creating
# replacement veth pairs. With --no-wait, OVS can remove an old port after the
# setup worker has already observed and reused it, producing a deterministic
# "Cannot find device" race during redeployment.
deploy_target="$SATNET_PLATFORM_ROOT/scripts/deploy.sh"
require_file "$deploy_target"
if grep -Fq -- "ovs-vsctl --no-wait --if-exists del-br" "$deploy_target"; then
    sed -i \
        's/ovs-vsctl --no-wait --if-exists del-br/ovs-vsctl --if-exists del-br/' \
        "$deploy_target"
    echo "compat_patch=bridge-delete-wait:applied"
else
    echo "compat_patch=bridge-delete-wait:already-applied"
fi

receiver_target="$SATNET_PLATFORM_ROOT/scripts/start_receiver.sh"
require_file "$receiver_target"
if grep -Fq -- 'BASE="$OWNER_HOME/yzy"' "$receiver_target"; then
    sed -i \
        's|BASE="$OWNER_HOME/yzy"|BASE="${SATNET_PLATFORM_ROOT:-$OWNER_HOME/yzy}"|' \
        "$receiver_target"
    echo "compat_patch=receiver-integration-root:applied"
else
    echo "compat_patch=receiver-integration-root:already-applied"
fi
