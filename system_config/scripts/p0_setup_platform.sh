#!/usr/bin/env bash
# P0: Intel Robotics AI Suite platform (ROS 2 Jazzy, OpenVINO, GPU/NPU user space) via robotics-installer.
# Run on PTL as the normal user: [PROXY=http://host:port NO_PROXY_EXTRA=10.0.0.0/8] ./system_config/scripts/p0_setup_platform.sh
set -eo pipefail

PROXY="${PROXY:-}"
NO_PROXY_LIST="localhost,127.0.0.1,::1${NO_PROXY_EXTRA:+,$NO_PROXY_EXTRA}"
INSTALLER_DIR="$HOME/robotics-setup"
INSTALLER_URL=https://amrdocs.intel.com/downloads/robotics-installer

log() { echo -e "\n=== $* ==="; }

if [ -n "$PROXY" ]; then
  log "Proxy"
  printf 'Acquire::http::Proxy "%s";\nAcquire::https::Proxy "%s";\n' "$PROXY" "$PROXY" \
    | sudo tee /etc/apt/apt.conf.d/95proxy >/dev/null
  if ! grep -q '^https_proxy=' /etc/environment; then
    printf 'http_proxy=%s\nhttps_proxy=%s\nno_proxy=%s\n' "$PROXY" "$PROXY" "$NO_PROXY_LIST" \
      | sudo tee -a /etc/environment >/dev/null
  fi
  export http_proxy="$PROXY" https_proxy="$PROXY" no_proxy="$NO_PROXY_LIST"
fi

log "Base update"
sudo apt-get update -q
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -q -o Dpkg::Options::=--force-confold
sudo apt-get install -y -q curl wget git

log "Download and verify robotics-installer"
mkdir -p "$INSTALLER_DIR" && cd "$INSTALLER_DIR"
wget -q -N "$INSTALLER_URL" "$INSTALLER_URL.sha256"
sha256sum -c robotics-installer.sha256
chmod +x robotics-installer

log "Run robotics-installer (about 40 min)"
args=(-auto -profile base -distro jazzy)
[ -n "$PROXY" ] && args+=(-proxy)
# A previous (partial) run leaves a state file; -resume skips completed stages.
[ -f /var/lib/robotics-installer/state.json ] && args+=(-resume)
sudo -E ./robotics-installer "${args[@]}"

log "Verify"
source /opt/ros/jazzy/setup.bash
python3 -c "import openvino as ov; print('OpenVINO', ov.__version__, ov.Core().available_devices)"
ls -l /dev/accel/accel0 || echo "WARNING: NPU device node missing"
echo "P0 done. Re-login so the 'render' group membership takes effect."
