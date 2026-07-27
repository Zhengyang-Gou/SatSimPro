#!/usr/bin/env bash

# One-time source import. Runtime entry points never call this script.
# Usage: import_sources.sh <dky_root> <lyh_root> <platform_root>

set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

DKY_IMPORT=${1:?missing D KY source directory}
LYH_IMPORT=${2:?missing LYH source directory}
PLATFORM_IMPORT=${3:?missing platform source directory}

for source_dir in "$DKY_IMPORT" "$LYH_IMPORT" "$PLATFORM_IMPORT"; do
    if [[ ! -d "$source_dir" ]]; then
        echo "source directory does not exist: $source_dir" >&2
        exit 2
    fi
    case "$(readlink -f "$source_dir")" in
        "$SATNET_BACKEND_ROOT"|"$SATNET_BACKEND_ROOT"/*)
            echo "import source must be outside the destination: $source_dir" >&2
            exit 2
            ;;
    esac
done

mkdir -p \
    "$SATNET_DKY_ROOT" \
    "$SATNET_LYH_ROOT" \
    "$SATNET_PLATFORM_ROOT" \
    "$SATNET_DATA_ROOT" \
    "$SATNET_STATE_DIR" \
    "$SATNET_LOG_DIR"

common_excludes=(
    --exclude='.git/'
    --exclude='__pycache__/'
    --exclude='*.pyc'
    --exclude='*.pcap'
    --exclude='logs/'
    --exclude='log/'
)

rsync -a "${common_excludes[@]}" \
    "$DKY_IMPORT/" "$SATNET_DKY_ROOT/"
rsync -a "${common_excludes[@]}" \
    "$LYH_IMPORT/" "$SATNET_LYH_ROOT/"

for item in \
    scripts test_utils test_scripts src include rawsocket \
    dpdk hiredis sqlite
do
    if [[ -e "$PLATFORM_IMPORT/$item" ]]; then
        rsync -a "${common_excludes[@]}" \
            "$PLATFORM_IMPORT/$item" "$SATNET_PLATFORM_ROOT/"
    fi
done
for item in README.MD README_new.MD; do
    if [[ -f "$PLATFORM_IMPORT/$item" ]]; then
        rsync -a "$PLATFORM_IMPORT/$item" "$SATNET_PLATFORM_ROOT/"
    fi
done
if [[ -d "$PLATFORM_IMPORT/data" ]]; then
    rsync -a "${common_excludes[@]}" \
        "$PLATFORM_IMPORT/data/" "$SATNET_DATA_ROOT/"
fi

# Vendor snapshots contain host-specific absolute paths. Rewrite only the
# imported copy so every active code reference stays inside satnet-backend.
mapfile -d '' text_files < <(
    grep -RIlZ . \
        "$SATNET_DKY_ROOT" \
        "$SATNET_LYH_ROOT" \
        "$SATNET_PLATFORM_ROOT" \
        --include='*.sh' --include='*.py' --include='*.c' \
        --include='*.h' --include='*.md' 2>/dev/null || true
)
if ((${#text_files[@]})); then
    sed -i \
        -e "s|/home/s223/lyh/sat_deploy|$SATNET_LYH_ROOT|g" \
        -e "s|/home/test/sat_deploy|$SATNET_LYH_ROOT|g" \
        -e "s|/home/s223/dky|$SATNET_DKY_ROOT|g" \
        -e "s|/home/test/dky|$SATNET_DKY_ROOT|g" \
        -e "s|/home/s223/yzy|$SATNET_PLATFORM_ROOT|g" \
        -e "s|/home/test/yzy|$SATNET_PLATFORM_ROOT|g" \
        "${text_files[@]}"
fi

find "$SATNET_BACKEND_ROOT" -type d -exec chmod 755 {} +
find "$SATNET_BACKEND_ROOT" -type f -exec chmod o-w {} +
chmod 755 "$SATNET_BACKEND_ROOT"/scripts/*.sh

printf 'source_import=ok\n'
printf 'dky=%s\n' "$SATNET_DKY_ROOT"
printf 'lyh=%s\n' "$SATNET_LYH_ROOT"
printf 'platform=%s\n' "$SATNET_PLATFORM_ROOT"
printf 'data=%s\n' "$SATNET_DATA_ROOT"
