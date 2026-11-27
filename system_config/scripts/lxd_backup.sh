#!/usr/bin/env bash
# Back up / restore the LXD containers (teleop, perception-ai, data) for moving to another PTL.
# Usage: sudo bash lxd_backup.sh export <dir>   # old PTL: <dir>/<container>.tar.gz (+ snapshots)
#        sudo bash lxd_backup.sh import <dir>   # new PTL, after P1; replaces the freshly created containers
set -euo pipefail

CONTAINERS=(teleop perception-ai data)
cmd="${1:?export|import}"
dir="${2:?backup directory}"

case "$cmd" in
  export)
    mkdir -p "$dir"
    for c in "${CONTAINERS[@]}"; do
      lxc export "$c" "$dir/$c.tar.gz"
    done
    ls -lh "$dir"
    ;;
  import)
    for c in "${CONTAINERS[@]}"; do
      if lxc info "$c" >/dev/null 2>&1; then
        lxc stop "$c" --force 2>/dev/null || true
        lxc delete "$c"
      fi
      lxc import "$dir/$c.tar.gz"
      lxc start "$c"
    done
    lxc list
    ;;
  *)
    echo "unknown command: $cmd" >&2
    exit 1
    ;;
esac
