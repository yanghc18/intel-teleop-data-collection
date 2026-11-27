#!/usr/bin/env bash
# P1: LXD Hybrid setup (host DDS config + 3 LXD containers with ROS2 Jazzy).
# Run on PTL from the repo root: sudo -E ./system_config/scripts/p1_setup_lxd.sh
set -euo pipefail

CFG_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONTAINERS=(teleop perception-ai data)
ROS_DOMAIN_ID=42
PROXY="${https_proxy:-}"
NO_PROXY_LIST="${no_proxy:-localhost,127.0.0.1}"
REAL_USER="${SUDO_USER:-$USER}"

log() { echo -e "\n=== $* ==="; }

log "Host: Cyclone DDS + ROS env"
apt-get install -y -q ros-jazzy-rmw-cyclonedds-cpp >/dev/null
install -D -m 644 "$CFG_DIR/dds/cyclonedds_host.xml" /etc/cyclonedds/host/cyclonedds.xml
install -D -m 644 "$CFG_DIR/dds/cyclonedds_lxd.xml"  /etc/cyclonedds/lxd/cyclonedds.xml
BASHRC="/home/$REAL_USER/.bashrc"
sed -i '/^export ROS_DOMAIN_ID=/d' "$BASHRC"
grep -q '# teleop-ros-env' "$BASHRC" || cat >> "$BASHRC" <<EOF
# teleop-ros-env
export ROS_DOMAIN_ID=$ROS_DOMAIN_ID
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///etc/cyclonedds/host/cyclonedds.xml
EOF

log "Host: dataset directory"
mkdir -p /data && chown "$REAL_USER:$REAL_USER" /data

log "Install LXD"
if [ -n "$PROXY" ]; then
  snap set system proxy.http="$PROXY" proxy.https="$PROXY"
fi
snap list lxd >/dev/null 2>&1 || snap install lxd
usermod -aG lxd "$REAL_USER"
lxd waitready

if ! lxc network show lxdbr0 >/dev/null 2>&1; then
  lxd init --preseed < "$CFG_DIR/lxd/preseed.yaml"
fi
if [ -n "$PROXY" ]; then
  lxc config set core.proxy_http "$PROXY"
  lxc config set core.proxy_https "$PROXY"
  lxc config set core.proxy_ignore_hosts "$NO_PROXY_LIST"
fi

log "LXD profiles"
for p in ros2-base teleop perception-ai data; do
  lxc profile show "$p" >/dev/null 2>&1 || lxc profile create "$p"
  lxc profile edit "$p" < "$CFG_DIR/lxd/profiles/$p.yaml"
done

provision() {
  local c="$1"
  lxc exec "$c" -- cloud-init status --wait >/dev/null 2>&1 || true
  if [ -n "$PROXY" ]; then
    lxc exec "$c" -- bash -c "cat > /etc/apt/apt.conf.d/95proxy <<EOF
Acquire::http::Proxy \"$PROXY\";
Acquire::https::Proxy \"$PROXY\";
EOF
grep -q '^https_proxy=' /etc/environment || printf 'http_proxy=%s\nhttps_proxy=%s\nno_proxy=%s\n' '$PROXY' '$PROXY' '$NO_PROXY_LIST' >> /etc/environment"
  fi
  # Reuse the host's ROS2 apt source/keyring installed by the Robotics AI Suite installer.
  for f in /etc/apt/sources.list.d/ros2.sources /usr/share/keyrings/ros2-archive-keyring.gpg; do
    [ -f "$f" ] && lxc file push "$f" "$c$f" --create-dirs
  done
  lxc exec "$c" -- bash -c "export DEBIAN_FRONTEND=noninteractive; apt-get update -q && apt-get upgrade -y -q && apt-get install -y -q ros-jazzy-ros-base ros-jazzy-rmw-cyclonedds-cpp ros-jazzy-demo-nodes-cpp >/dev/null"
  lxc exec "$c" -- bash -c "grep -q 'jazzy/setup.bash' /root/.bashrc || echo 'source /opt/ros/jazzy/setup.bash' >> /root/.bashrc"
}

log "Containers"
for c in "${CONTAINERS[@]}"; do
  if ! lxc info "$c" >/dev/null 2>&1; then
    lxc launch ubuntu:24.04 "$c" -p default -p ros2-base -p "$c"
  fi
  provision "$c"
  lxc snapshot "$c" p1-baseline --reuse
done

lxc list
echo "P1 setup done. Re-login (or 'newgrp lxd') to use lxc without sudo."
