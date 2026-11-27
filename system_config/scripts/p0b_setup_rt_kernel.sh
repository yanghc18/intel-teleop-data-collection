#!/usr/bin/env bash
# P0b: Intel ECI PREEMPT_RT kernel + CPU isolation for the control loop. Needs the ECI apt repo added by P0.
# Run on PTL as the normal user, then reboot: [ISOL_CPUS=2-3] bash system_config/scripts/p0b_setup_rt_kernel.sh
# ISOL_CPUS= (empty) skips CPU isolation. The generic kernel stays installed: to roll back, pick it under
# "Advanced options for Ubuntu" in the GRUB menu (shown 5 s), or remove /etc/default/grub.d/90-rt-kernel.cfg + update-grub.
set -euo pipefail

PKG=linux-intel-rt-experimental
# P-cores are 0-3 on the 368H (/sys/devices/cpu_core/cpus); keep 0-1 for housekeeping.
ISOL_CPUS="${ISOL_CPUS-2-3}"
GRUB_CFG=/etc/default/grub.d/90-rt-kernel.cfg

log() { echo -e "\n=== $* ==="; }

if mokutil --sb-state 2>/dev/null | grep -q 'SecureBoot enabled'; then
  echo "Secure Boot is enabled; the ECI kernel may not boot. Disable Secure Boot in the BIOS and re-run." >&2
  exit 1
fi

log "Install $PKG and rt-tests"
sudo apt-get update -q
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q "$PKG" rt-tests
KVER="$(basename "$(ls -1 /boot/vmlinuz-*-rt | sort -V | tail -1)")"
KVER="${KVER#vmlinuz-}"

log "GRUB: default $KVER, CPU isolation '${ISOL_CPUS:-none}'"
ARGS="quiet splash"
[ -n "$ISOL_CPUS" ] && ARGS+=" isolcpus=nohz,domain,managed_irq,$ISOL_CPUS nohz_full=$ISOL_CPUS rcu_nocbs=$ISOL_CPUS"
sudo tee "$GRUB_CFG" >/dev/null <<EOF
GRUB_DEFAULT="Advanced options for Ubuntu>Ubuntu, with Linux $KVER"
GRUB_TIMEOUT_STYLE=menu
GRUB_TIMEOUT=5
GRUB_CMDLINE_LINUX_DEFAULT="$ARGS"
EOF
sudo update-grub
sudo grep -q "with Linux $KVER'" /boot/grub/grub.cfg || { echo "GRUB entry for $KVER not found" >&2; exit 1; }

cat <<EOF

RT kernel $KVER installed and set as default. Reboot, then verify:
  uname -v | grep PREEMPT_RT
  cat /sys/devices/system/cpu/isolated            # expect: ${ISOL_CPUS:-<empty>}
  python3 -c "import openvino as ov; print(ov.Core().available_devices)"   # expect CPU, GPU, NPU
  sudo cyclictest -m -Sp90 -i1000 -D 10m          # equipment test T0
EOF
