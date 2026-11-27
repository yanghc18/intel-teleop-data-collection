#!/usr/bin/env bash
# Provision a new PTL with the whole host setup: P0 platform -> P1 LXD + DDS -> P2 ROS 2 workspace -> P4 teleop container.
# Run as the normal user from the repo root (needs sudo):
#   [PROXY=http://host:port NO_PROXY_EXTRA=<subnets>] bash system_config/scripts/setup_ptl.sh [--from p0|p1|p2|p4]
# Each step is idempotent; after a failure, fix the cause and re-run with --from <step>.
set -eo pipefail

SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
FROM=p0
[ "${1:-}" = "--from" ] && FROM="${2:?--from needs p0|p1|p2|p4}"

run_step() {
  local step="$1"; shift
  [[ "$step" < "$FROM" ]] && { echo "--- skip $step"; return; }
  echo -e "\n######## $step: $* (log: ~/setup_$step.log)"
  "$@" 2>&1 | tee ~/"setup_$step.log"
}

chmod +x "$SCRIPTS"/*.sh
run_step p0 "$SCRIPTS/p0_setup_platform.sh"
# P1 reads the proxy from the environment written by P0.
set -a; . /etc/environment; set +a
run_step p1 sudo -E "$SCRIPTS/p1_setup_lxd.sh"
run_step p2 "$SCRIPTS/p2_setup_ws.sh"
run_step p4 sudo bash "$SCRIPTS/p4_setup_teleop_lxd.sh"

cat <<'EOF'

Host setup done. Remaining manual steps:
  1. Re-login (groups: render, lxd, realtime).
  2. CAN adapters: sudo ./system_config/scripts/can_setup.sh   (plug in arm_r, arm_l, hand_r, hand_l when asked)
  3. Optional: restore LXD containers / data from the old PTL (see docs/setup_steps.md, "Migrating to a new PTL").
  4. Before real hardware: RT kernel, bash system_config/scripts/p0b_setup_rt_kernel.sh, then reboot.
EOF
