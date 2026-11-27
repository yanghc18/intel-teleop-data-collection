# Setup Steps (P0 / P1)

Reproducible record of what was actually executed on the PTL. Each step notes whether it is
**host-only** (kernel / driver / device level) or **containerizable** (can go into a Dockerfile later).

| Item | Value |
|---|---|
| CPU | Intel Core Ultra X7 368H (Panther Lake) |
| OS | Ubuntu 24.04.5 LTS |
| Kernel | 7.0.0-31-generic (RT kernel deferred, see [RT kernel](#rt-kernel-deferred)) |
| Intel Robotics AI Suite | 2026.3, `robotics-installer` profile `base`, ROS 2 Jazzy |
| Date | 2026-11-27 |

---

## P0 Platform Setup

Follows Intel Robotics AI Suite [Getting Started](https://developer.robotics.intel.com/2026.3/development-stack/platform_foundation/getting_started/).

### P0.1 Proxy (corporate network only) - host-only

Proxy discovered from the corporate WPAD/PAC file. Replace `<PROXY>` with `http://host:port`.

```bash
sudo tee /etc/apt/apt.conf.d/95proxy <<'EOF'
Acquire::http::Proxy "<PROXY>";
Acquire::https::Proxy "<PROXY>";
EOF

sudo tee -a /etc/environment <<'EOF'
http_proxy=<PROXY>
https_proxy=<PROXY>
no_proxy=localhost,127.0.0.1,::1,<LOCAL_SUBNETS>
EOF
```

Load into the current shell without re-login: `set -a; . /etc/environment; set +a`.

Dockerfile: `ARG http_proxy https_proxy no_proxy` (build args are honored by apt / pip / curl).

### P0.2 Base update - containerizable

```bash
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -o Dpkg::Options::=--force-confold
sudo apt-get install -y curl wget git
```

### P0.3 Download and verify the installer

```bash
mkdir -p ~/robotics-setup && cd ~/robotics-setup
wget https://amrdocs.intel.com/downloads/robotics-installer
wget https://amrdocs.intel.com/downloads/robotics-installer.sha256
sha256sum -c robotics-installer.sha256
chmod +x robotics-installer
```

### P0.4 Run the installer (non-interactive)

```bash
# Preview stages
sudo -E ./robotics-installer -auto -profile base -distro jazzy -proxy -dry-run
# Install (~40 min with proxy)
sudo -E ./robotics-installer -auto -profile base -distro jazzy -proxy
```

- `-auto` avoids the TUI (required when running over non-interactive SSH).
- `-proxy` passes `http_proxy`/`https_proxy` to OpenVINO pip downloads.
- Log: `/var/log/robotics-installer/install-<timestamp>.log`; state: `/var/lib/robotics-installer/state.json`.
- If it fails, re-run with `-resume` to skip completed stages.
- Use `-dry-run -debug` to print the exact command of every stage.

### P0.5 What the installer does (Dockerfile reference)

Repositories added (keyrings are fetched by the installer into `/usr/share/keyrings/` and `/etc/apt/keyrings/`):

| Repo | Source line | Keyring |
|---|---|---|
| Intel AMR | `deb https://amrdocs.intel.com/repos/noble amr main` | `eci-archive-keyring.gpg` |
| Intel oneAPI | `deb https://apt.repos.intel.com/oneapi all main` | `oneapi-archive-keyring.gpg` |
| Intel OpenVINO | `deb https://apt.repos.intel.com/openvino ubuntu24 main` | `openvino-archive-keyring.gpg` |
| Intel graphics PPA | `ppa:kobuk-team/intel-graphics` | (PPA) |
| ROS 2 | `ros2-apt-source_1.3.0.noble_all.deb` from `ros-infrastructure/ros-apt-source` | inline in `ros2.sources` |
| Gazebo | `deb https://packages.osrfoundation.org/gazebo/ubuntu-stable noble main` | `pkgs-osrf-archive-keyring.gpg` |
| RealSense | `deb https://librealsense.realsenseai.com/Debian/apt-repo noble main` | `/etc/apt/keyrings/librealsenseai.gpg` |

Apt pins (`/etc/apt/preferences.d/`):

| File | Pin |
|---|---|
| `amr` | `origin amrdocs.intel.com`, priority 1001 |
| `oneapi` | `intel-oneapi-{runtime,compiler,mkl}-*` version `2026.*`, priority 1001 |
| `intel-openvino` | `openvino`, `openvino-libraries-dev` `2025.3.0*` (1001); `ros-jazzy-openvino-{node,wrapper-lib}` `2025.3.0*` (1002) |

Packages by stage:

| Stage | Packages / action | Host-only / Container |
|---|---|---|
| Prerequisites | `software-properties-common curl`, `add-apt-repository universe` | Container |
| ROS 2 | `ros-jazzy-desktop` | Container |
| Shell env | `source /opt/ros/jazzy/setup.bash`, `ROS_DOMAIN_ID=39` in `.bashrc` (overridden to 42 in P1) | Container (ENV) |
| Gazebo | `gz-harmonic` | Container (optional) |
| GPU user space | `libze1 libze-intel-gpu1` | Container (+ `--device /dev/dri`) |
| OpenVINO | `openvino` | Container |
| ROS OpenVINO node | debconf `openvino-node/pip-proxy=true`, `openvino-node/models=true`; `ros-jazzy-openvino-node` (downloads ~1 GB demo models to `/opt/openvino_toolkit/models`) | Container (set `models=false` to shrink image) |
| Robotics SDK | `ros-jazzy-robotics-sdk` | Container |
| Firmware | `linux-firmware` | **Host-only** |
| RealSense | `ros-jazzy-librealsense2 librealsense2 librealsense2-dkms` | `librealsense2-dkms` **host-only**; others container |
| Collaborative SLAM | `ros-jazzy-collab-slam-lze` | Container (not used in this project) |
| NPU | `intel-level-zero-npu intel-driver-compiler-npu` | Container user space (+ `--device /dev/accel/accel0`); kernel driver is in-tree |
| NPU udev | `/etc/udev/rules.d/10-intel-vpu.rules`: `SUBSYSTEM=="accel", KERNEL=="accel*", GROUP="render", MODE="0660"` | **Host-only** |
| Groups | `usermod -aG render $USER` | Host (container: `--group-add render`) |

### P0.6 Verification

```bash
source /opt/ros/jazzy/setup.bash
ros2 pkg list | wc -l                                   # 526
ros2 pkg list | grep -E "openvino|realsense"            # openvino_node, realsense2_camera, ...
python3 -c "import openvino as ov; print(ov.__version__, ov.Core().available_devices)"
# 2025.3.0 ['CPU', 'GPU', 'NPU']
ls -l /dev/accel/accel0                                 # crw-rw---- root render
id                                                      # includes render
```

Known harmless warnings: `ldconfig: /opt/intel/oneapi/redist/lib/*.so is not a symbolic link`.

### RT kernel (deferred)

Not installed yet. P2-P4 are being developed with mock hardware and do not need it.
When needed, follow the Intel guide "Enabling Real-time Linux kernel" (ECI `linux-intel-rt-*`),
check Secure Boot state first, reboot, and verify `uname -a` shows `PREEMPT_RT`.

---

## P1 Containers and DDS Networking

All files are in [`system_config/`](../system_config):

| File | Purpose |
|---|---|
| `dds/cyclonedds_host.xml` | Cyclone DDS on host, interface `lxdbr0` |
| `dds/cyclonedds_lxd.xml` | Cyclone DDS inside containers, interface `eth0` |
| `lxd/preseed.yaml` | `lxdbr0` 10.100.0.1/24 (NAT, no IPv6), 100 GiB btrfs pool `default` |
| `lxd/profiles/ros2-base.yaml` | `ROS_DOMAIN_ID=42`, `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp`, `CYCLONEDDS_URI`, read-only mount of `/etc/cyclonedds/lxd` |
| `lxd/profiles/teleop.yaml` | 8 GiB; Manus dongle USB passthrough (TODO: vendor/product id) |
| `lxd/profiles/perception-ai.yaml` | 24 GiB, `security.nesting=true`, `gpu` device, NPU `unix-char /dev/accel/accel0`, USB D435i `8086:0b3a`, D405 `8086:0b5b` |
| `lxd/profiles/data.yaml` | 8 GiB, host `/data` mounted at `/data` with `shift: "true"` |
| `scripts/p1_setup_lxd.sh` | Idempotent setup script (below) |

### P1.1 Run

```bash
cd ~/intel-teleop-data-collection
set -a; . /etc/environment; set +a
sudo -E ./system_config/scripts/p1_setup_lxd.sh 2>&1 | tee ~/p1_setup.log
newgrp lxd   # or re-login, to use lxc without sudo
```

### P1.2 What the script does

1. **Host**: install `ros-jazzy-rmw-cyclonedds-cpp`; install DDS XMLs to `/etc/cyclonedds/{host,lxd}/cyclonedds.xml`;
   replace `ROS_DOMAIN_ID` in `~/.bashrc` with a `# teleop-ros-env` block (domain 42, Cyclone DDS, host XML); create `/data`.
2. **LXD**: set snap proxy, `snap install lxd`, add user to `lxd` group, `lxd init --preseed`, set `core.proxy_*`.
3. **Profiles**: create/update `ros2-base`, `teleop`, `perception-ai`, `data`.
4. **Containers** `teleop`, `perception-ai`, `data` (`ubuntu:24.04`, profiles `default` + `ros2-base` + own):
   - apt proxy + `/etc/environment` proxy
   - push host `/etc/apt/sources.list.d/ros2.sources` (key is inline)
   - `apt-get upgrade`, install `ros-jazzy-ros-base ros-jazzy-rmw-cyclonedds-cpp ros-jazzy-demo-nodes-cpp`
   - `source /opt/ros/jazzy/setup.bash` in `/root/.bashrc`
   - snapshot `p1-baseline`

Dockerfile equivalent per container: `FROM ros:jazzy-ros-base` + `ros-jazzy-rmw-cyclonedds-cpp`;
`ENV ROS_DOMAIN_ID=42 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp CYCLONEDDS_URI=file:///etc/cyclonedds/cyclonedds.xml`;
mount the DDS XML; devices via `--device` (`/dev/dri`, `/dev/accel/accel0`, `/dev/bus/usb`).
Note: Docker bridge networks do not pass multicast well; use `--network host` or adjust the DDS XML (peers / interface).

### P1.3 Verification

DDS (host shell has the `# teleop-ros-env` block; containers get env from the `ros2-base` profile):

```bash
# Host talker -> container listener
ros2 run demo_nodes_cpp talker &
lxc exec teleop -- bash -lc 'source /opt/ros/jazzy/setup.bash; ros2 topic echo /chatter --once'
# Container talker -> host listener
lxc exec teleop -- bash -lc 'source /opt/ros/jazzy/setup.bash; ros2 run demo_nodes_cpp talker' < /dev/null &
ros2 topic echo /chatter --once
```

| Direction | Result |
|---|---|
| host <-> teleop | OK both ways |
| host <-> perception-ai | OK both ways |
| host <-> data | OK both ways |
| teleop -> data (container to container) | OK |

Devices:

| Check | Result |
|---|---|
| `perception-ai`: `ls -l /dev/dri /dev/accel` | `card1`, `renderD128`, `accel0` present (device level only; OpenVINO runtime inside the container is verified in P5/P7) |
| `data`: `df -h /data`, write test | Host NVMe mounted; writable after adding `shift: "true"` |
| RealSense / Manus USB | Not tested (devices not available yet); RealSense USB entries are hot-plug |

All three containers have snapshot `p1-baseline`.

---

## Pitfalls

| Symptom | Cause / Fix |
|---|---|
| No internet on PTL | Corporate proxy required; see P0.1 |
| Installer TUI hangs over SSH | Use `-auto -profile base -distro jazzy` |
| `pkill -f robotics-installer` kills your own SSH session | The pattern matches the SSH command line; use `pgrep -a` first and kill by PID |
| Scripts fail with `$'\r': command not found` | Files edited on Windows; run `sed -i 's/\r$//'` on them |
| Long jobs die when SSH drops | Run with `nohup ... &` and log to a file |
| Host `/data` shows `nobody:nogroup` in container and is read-only | Unprivileged container UID mapping; add `shift: "true"` to the disk device (idmapped mount) |
| `lxc restart` hangs | Use `lxc restart <c> --force` |
| Script piped via `bash -s` stops after an `lxc exec` line | `lxc exec` consumes stdin; add `< /dev/null` |
| First DDS echo after starting a talker gets nothing | Discovery takes a few seconds; wait ~4 s before echo |
