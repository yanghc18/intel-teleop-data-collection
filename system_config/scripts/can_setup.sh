#!/usr/bin/env bash
# Bring up the 4 CAN buses (all classic CAN 1 Mbps): arm_r/arm_l = Anvil OpenArm 2.0, hand_r/hand_l = Linker O6.
# Usage: sudo ./can_setup.sh            # real USB-CAN adapters (first run: plug in one by one when prompted)
#        sudo ./can_setup.sh --virtual  # vcan interfaces with the same names, for testing without hardware
set -euo pipefail

IFACES=(arm_r arm_l hand_r hand_l)
ANVIL_SETUP="$(cd "$(dirname "$0")/../.." && pwd)/ros2_ws/third_party/anvil-openarm/scripts/setup_can.sh"

if [[ "${1:-}" == "--virtual" ]]; then
  modprobe vcan
  for i in "${IFACES[@]}"; do
    ip link show "$i" &>/dev/null || ip link add dev "$i" type vcan
    ip link set "$i" up
  done
else
  # Anvil's script: persistent names via udev (USB serial) + systemd-networkd at 1 Mbps.
  bash "$ANVIL_SETUP" "${IFACES[@]}"
fi

ip -brief link show | grep -E "^($(IFS='|'; echo "${IFACES[*]}"))\b"
