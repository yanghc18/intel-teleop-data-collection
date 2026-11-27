#!/usr/bin/env bash
# P2: build the host ROS 2 workspace (OpenARM 2.0 + Linker O6, mock hardware by default).
# Run on PTL as the normal user (uses sudo for apt): ./system_config/scripts/p2_setup_ws.sh
set -eo pipefail

WS="$(cd "$(dirname "$0")/../../ros2_ws" && pwd)"

log() { echo -e "\n=== $* ==="; }

log "Host packages"
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q \
  python3-colcon-common-extensions python3-rosdep python3-vcstool can-utils \
  ros-jazzy-joint-state-publisher-gui ros-jazzy-rqt-joint-trajectory-controller \
  ros-jazzy-rqt-controller-manager >/dev/null
[ -f /etc/ros/rosdep/sources.list.d/20-default.list ] || sudo rosdep init
rosdep update >/dev/null

log "Realtime limits for ros2_control_node (SCHED_FIFO + memlock; effective after re-login)"
getent group realtime >/dev/null || sudo groupadd realtime
sudo usermod -aG realtime "$USER"
printf '@realtime soft rtprio 99\n@realtime soft priority 99\n@realtime soft memlock unlimited\n@realtime hard rtprio 99\n@realtime hard priority 99\n@realtime hard memlock unlimited\n' \
  | sudo tee /etc/security/limits.d/90-realtime.conf >/dev/null

log "Upstream sources"
cd "$WS"
mkdir -p third_party
touch third_party/COLCON_IGNORE  # linkerhand-urdf has catkin package.xml files colcon would try to build
vcs import --skip-existing src < upstream.repos
vcs import --skip-existing third_party < third_party.repos

log "rosdep + colcon build"
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths src --ignore-src -y -r
colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release

log "P2 workspace ready: source $WS/install/setup.bash"
