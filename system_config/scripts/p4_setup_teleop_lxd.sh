#!/usr/bin/env bash
# P4: build the teleop packages (teleop_msgs, teleop_retargeting, pico_bridge) inside the LXD 'teleop' container.
# Run on PTL from the repo root after P1/P2: sudo bash system_config/scripts/p4_setup_teleop_lxd.sh
# Re-run after changing the teleop sources (the workspace in the container is rebuilt from a fresh copy).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
C=teleop
PACKAGES=(teleop_msgs teleop_retargeting pico_bridge)

log() { echo -e "\n=== $* ==="; }
in_c() { lxc exec "$C" -- bash -c "set -a; . /etc/environment; set +a; $1" < /dev/null; }

log "Build tools in $C"
in_c "DEBIAN_FRONTEND=noninteractive apt-get install -y -q python3-colcon-common-extensions python3-rosdep build-essential >/dev/null
[ -f /etc/ros/rosdep/sources.list.d/20-default.list ] || rosdep init
rosdep update >/dev/null"

log "Copy sources"
in_c "rm -rf /root/teleop_ws/src && mkdir -p /root/teleop_ws/src"
for p in "${PACKAGES[@]}"; do
  lxc file push -r "$REPO/ros2_ws/src/teleop/$p" "$C/root/teleop_ws/src/"
done

log "rosdep + colcon build"
in_c "cd /root/teleop_ws && source /opt/ros/jazzy/setup.bash \
  && rosdep install --from-paths src --ignore-src -y -r \
  && colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release"
in_c "grep -q teleop_ws/install /root/.bashrc || echo 'source /root/teleop_ws/install/setup.bash' >> /root/.bashrc"

lxc snapshot "$C" p4-teleop --reuse
echo "Teleop workspace ready in $C: lxc exec $C -- bash -ic 'ros2 launch teleop_retargeting teleop.launch.py'"
