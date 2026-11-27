# Setup Steps (P0 / P1 / P2 / P3 / P4)

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
Automated by [`p0_setup_platform.sh`](../system_config/scripts/p0_setup_platform.sh); see also [Migrating to a new PTL](#migrating-to-a-new-ptl).

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

## P2 Hardware Drivers (mock hardware)

No arms/hands are available yet, so P2 runs `ros2_control` with `mock_components/GenericSystem`.
The same URDF/launch switches to the real CAN drivers with `use_mock_hardware:=false`.

Hardware:

| Item | Detail |
|---|---|
| Arms | Anvil Robotics OpenArm 2.0 ([anvil-robotics/openarm](https://github.com/anvil-robotics/openarm)) = Enactic OpenArm v2.0 design; Damiao motors J1-J7 (DM8009 x2, DM4340 x2, DM4310 x3), same CAN IDs as Enactic (slave 0x01-0x07, master 0x11-0x17) |
| Arm CAN | candleLight USB-CAN (gs_usb), **classic CAN 1 Mbps** (no CAN-FD) -> `can_fd=false` |
| Hands | Linker Bot O6 x2, 6 actuated joints each (+5 mimic joints), CAN 1 Mbps ([linkerhand-ros2-sdk](https://github.com/linker-bot/linkerhand-ros2-sdk)) |
| CAN names | `arm_r`, `arm_l`, `hand_r`, `hand_l` (udev rule by USB serial) |

### P2.1 Workspace layout

The ROS 2 workspace is `ros2_ws/` in this repo:

| Path | Content |
|---|---|
| `ros2_ws/upstream.repos` | `openarm_description`, `openarm_ros2` (`openarm_hardware`, `openarm_bringup`, ...), `openarm_can` - pinned commits, imported into `src/` |
| `ros2_ws/third_party.repos` | `linkerhand-urdf` (O6 URDF/meshes), `anvil-openarm` (vendor CAN/motor tools), `linkerhand-ros2-sdk` (O6 protocol reference) - imported into `third_party/` (outside `src/`: `linkerhand-urdf` has invalid catkin `package.xml` files that break `rosdep` and `colcon`) |
| `src/description/openarm_o6_description` | Combined URDF: bimanual OpenArm v2.0 (own preset, no grippers) + O6 left/right at the arm `ee_mount_point` (link7 +20.5 mm x, pitch 90 deg; hand roll to be confirmed on hardware). Generates O6 URDFs at build time with `package://` mesh paths and prefixed material names |
| `src/hardware/openarm_o6_bringup` | `controllers.yaml` + `bringup.launch.py` |
| `src/hardware/linker_o6_hardware` | ros2_control `SystemInterface` for the O6 over SocketCAN (see P2.6) + `fake_o6.py` simulator |

### P2.2 Build

```bash
cd ~/intel-teleop-data-collection
./system_config/scripts/p2_setup_ws.sh 2>&1 | tee ~/p2_setup.log
```

The script:

1. Installs `python3-colcon-common-extensions python3-rosdep python3-vcstool can-utils ros-jazzy-joint-state-publisher-gui ros-jazzy-rqt-joint-trajectory-controller ros-jazzy-rqt-controller-manager`; `rosdep init/update`.
   (`ros-jazzy-moveit` was also installed on the PTL for P4.)
2. Creates group `realtime` with `/etc/security/limits.d/90-realtime.conf` (`rtprio 99`, `memlock unlimited`) and adds the user (re-login needed) so `ros2_control_node` can use `SCHED_FIFO`. **Host-only.**
3. `vcs import` both `.repos` files; `touch third_party/COLCON_IGNORE`.
4. `rosdep install --from-paths src --ignore-src -y -r` (pulls `ros-jazzy-zed-description` among others).
5. `colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release`.

Dockerfile equivalent: `FROM ros:jazzy-ros-base`, same apt packages, `COPY ros2_ws`, `vcs import`, `rosdep install`, `colcon build`;
run with `--network host --cap-add SYS_NICE --ulimit rtprio=99 --ulimit memlock=-1` (CAN is a host netdev, so the control container needs host networking).

### P2.3 CAN interfaces

```bash
sudo ./system_config/scripts/can_setup.sh --virtual   # vcan arm_r/arm_l/hand_r/hand_l (no hardware)
sudo ./system_config/scripts/can_setup.sh             # real adapters: Anvil setup_can.sh asks to plug them in one by one,
                                                      # writes /etc/udev/rules.d/90-can.rules + systemd-networkd 1 Mbps
```

**Host-only** (udev, kernel netdev). Plug order on first run: right arm, left arm, right hand, left hand.

### P2.4 Run

```bash
source ros2_ws/install/setup.bash
ros2 launch openarm_o6_bringup bringup.launch.py                       # mock (default), add rviz:=true on the desktop
ros2 launch openarm_o6_bringup bringup.launch.py use_mock_hardware:=false   # real arms + real O6
ros2 launch openarm_o6_bringup bringup.launch.py use_mock_hands:=false      # mock arms + real (or fake) O6
ros2 launch openarm_o6_description display.launch.py                  # URDF preview with joint sliders
```

Controllers (`controller_manager` `update_rate: 1000`), `mode:=manual` (default):

| Controller | Type | State at start | Use |
|---|---|---|---|
| `{left,right}_{arm,hand}_state_broadcaster` | JointStateBroadcaster (500 Hz), one per hardware component | active | `/joint_states` |
| `{left,right}_arm_trajectory_controller` | JointTrajectoryController | active | P2 manual jog (rqt), MoveIt, replay |
| `{left,right}_hand_trajectory_controller` | JointTrajectoryController | active | P2 manual jog of O6 |
| `{left,right}_arm_controller` | JointGroupPositionController | inactive | streaming commands from `teleop_safety` (`mode:=teleop`) |
| `{left,right}_gripper_controller` | JointGroupPositionController | inactive | O6 commands from `teleop_safety` (`mode:=teleop`) |

Manual jog: `ros2 run rqt_joint_trajectory_controller rqt_joint_trajectory_controller` (desktop), or

```bash
ros2 action send_goal /left_arm_trajectory_controller/follow_joint_trajectory control_msgs/action/FollowJointTrajectory \
  "{trajectory: {joint_names: [openarm_left_joint1, openarm_left_joint4], points: [{positions: [0.5, 1.0], time_from_start: {sec: 2}}]}}"
```

Teleop mode (P3): `ros2 launch openarm_o6_bringup bringup.launch.py mode:=teleop` activates the forward controllers instead and starts `safety_monitor_node`.

### P2.5 Verification (mock, 2026-11-27)

| Check | Result |
|---|---|
| `check_urdf` | OK, root `world`; 4 `ros2_control` systems |
| Real-mode URDF params | arms: `openarm_hardware/OpenArmHW`, `can_interface=arm_r/arm_l`, `can_fd=False`, `hand=False`, kp/kd from upstream |
| `ros2 control list_hardware_components` | 4 mock systems active |
| `ros2 control list_controllers` | 5 active, 4 inactive as above (single broadcaster at that time; 8 active since P3) |
| `/joint_states` | 500 Hz, 26 joints (14 arm + 12 hand) |
| Trajectory goals (arm, hand) | SUCCEEDED, positions reached |
| O6 mimic joints | `rh_index_dip` = 0.89 x `rh_index_mcp_pitch` via `robot_state_publisher` |
| vcan | `cansend`/`candump` on `arm_r` OK |
| `SCHED_FIFO` | `Successful set up FIFO RT scheduling policy with priority 50` |
| 1 kHz loop (generic kernel, 2 min) | controller periodicity avg 1004 Hz, std 65 Hz, min 788 Hz (period max ~1.27 ms); CM cycle total ~70-190 us. Jitter is expected without PREEMPT_RT/isolcpus; re-measure after the RT kernel |

Loop statistics are read from `/controller_manager/statistics/{names,values}` (`pal_statistics_msgs`, values topic is best-effort QoS).

### P2.6 O6 driver `linker_o6_hardware`

C++ ros2_control plugin `linker_o6_hardware/LinkerO6System`, protocol ported from the official Python SDK
([linkerhand-ros2-sdk](https://github.com/linker-bot/linkerhand-ros2-sdk) `core/can/linker_hand_o6_can.py`, `utils/mapping.py`):

| Item | Value |
|---|---|
| CAN ID (11-bit) | right `0x27`, left `0x28` (override with param `can_id`) |
| Frame | `data[0]` = command, `data[1..6]` = one byte per joint |
| Byte order | thumb_cmc_pitch, thumb_cmc_yaw, index, middle, ring, pinky |
| `0x01` | 6 bytes = set target; no payload = request; reply `0x01` + 6 bytes = current position |
| `0x02` / `0x05` | torque limit / speed (0-255), sent on activate |
| Units | `rad = (255 - raw) / 255 * max`, `max` = URDF upper limit (0.58 / 1.36 / 1.6 rad, same as SDK); 255 = open |

Behavior:

- On activate: set speed/torque, read the current pose and use it as the initial command (no jump at start). Fails if no reply within ~500 ms.
- `write()`: sends a position frame at most `command_rate_hz` and only when the target changed; polls the position at `state_rate_hz`.
  Both default to 60 Hz like the SDK node; the real limit is to be measured on hardware.
- `read()`: non-blocking; returns ERROR if no position report for `state_timeout_ms` (200). ros2_control then deactivates the component and its controllers.
- Parameters are in [`linker_o6.ros2_control.xacro`](../ros2_ws/src/description/openarm_o6_description/urdf/linker_o6.ros2_control.xacro).

Test without the hand (vcan + simulator):

```bash
sudo ./system_config/scripts/can_setup.sh --virtual
ros2 run linker_o6_hardware fake_o6.py --channel hand_r --side right &
ros2 run linker_o6_hardware fake_o6.py --channel hand_l --side left &
ros2 launch openarm_o6_bringup bringup.launch.py use_mock_hands:=false
colcon test --packages-select linker_o6_hardware   # protocol unit tests
```

| Check (fake O6 on vcan) | Result |
|---|---|
| Unit tests (mapping vs SDK, frame layout, parsing) | 4/4 pass |
| Activation | both hands active; initial state = fake power-on pose (`thumb_cmc_pitch` 0.125, `pinky` 0.471 rad), no motion |
| Trajectory goal | SUCCEEDED; `rh_index_mcp_pitch` 1.198 (target 1.2, 1 raw step = 0.006 rad) |
| Bus traffic idle | 59 polls/s + 59 replies/s; no position frames while the target is unchanged |
| Fake hand stopped | after 200 ms: `no position report`, component -> unconfigured, `right_hand_trajectory_controller` and `joint_state_broadcaster` deactivated |
| Recovery | restart fake, `ros2 control set_hardware_component_state linker_o6_right_hardware_interface active`, `switch_controllers --activate ...` OK |

Note: with the single `joint_state_broadcaster` used at that time, one hand failing also stopped `/joint_states` for the arms.
Fixed in P3 with one broadcaster per hardware component.

To do with the real hand: `candump hand_r` while the official SDK runs to confirm IDs/frames/reply behavior;
verify direction and linearity of the mapping per finger; measure the max poll/command rate; check fault codes (`0x35`).

### P2.7 Pending (needs hardware)

- Run `can_setup.sh` with real adapters; Anvil motor test (`python -m openarm.damiao.monitor`, [motor-testing.md](https://github.com/anvil-robotics/openarm/blob/main/motor-testing.md)) and zero calibration.
- Confirm the Anvil arms run with `openarm_hardware` at `can_fd=false` and without the J8 gripper motor (`hand=False`); confirm joint directions/limits (Anvil `openarm2` J6 range is wider than the URDF +-45 deg).
  Read `openarm_hardware` activation code first (possible return-to-zero motion on start).
- Arm CAN bandwidth: 7 motors x (command + reply) per cycle on classic CAN 1 Mbps is ~1.6-1.9 ms, so ~500 Hz per bus is the expected ceiling. Keep `update_rate: 1000` for now and decide after measuring.
- O6: see P2.6 "To do with the real hand".
- Confirm O6 mounting roll and flange offset, and the arm mounting on the actual stand (URDF uses the Enactic v2 body); RViz check on the desktop.
- 1 kHz jitter with real CAN after the RT kernel.

---

## P3 Safety Layer

Packages:

| Package | Content |
|---|---|
| `src/teleop/teleop_msgs` | `TeleopAction` (deadman + joint targets for left/right arm and hand), `SafetyState` |
| `src/teleop/teleop_safety` | `safety_monitor_node` (C++, host, 500 Hz), `config/safety.yaml`, `scripts/safety_test.py` (acceptance test), unit tests |

Data flow (`mode:=teleop`):

```
/teleop_action (TeleopAction, from retargeting / VLA)  --+
/emergency_stop (std_msgs/Bool, transient local)       --+--> safety_monitor_node --> /{left,right}_arm_controller/commands
/joint_states                                          --+          500 Hz            /{left,right}_gripper_controller/commands
                                                                                      /teleop/safety_state (50 Hz + on change)
```

### P3.1 Behavior

| Function | Implementation |
|---|---|
| States | `ACTIVE` (forward limited targets), `HOLD` (freeze outputs), `ESTOP` (freeze, latched) |
| Command timeout | no `/teleop_action` for `command_timeout` = 80 ms -> `HOLD` (80 ms + one 2 ms cycle < 100 ms requirement) |
| Deadman | `TeleopAction.deadman == false` -> `HOLD` |
| E-stop | `/emergency_stop` true -> `ESTOP`, latched; clear with `/emergency_stop` false **and** `ros2 service call /safety_monitor/reset std_srvs/srv/Trigger` (refused while still pressed) |
| Soft joint limits | URDF limits minus `soft_limit_margin` (0.02 rad) |
| Velocity limit | per joint `min(URDF velocity, group max_velocity)` (arms 1.0, hands 2.0 rad/s); also interpolates 100 Hz targets to 500 Hz |
| Workspace | KDL FK of `world -> openarm_{left,right}_link7`, axis-aligned box per arm; a step is rejected if it moves the tip farther outside the box (motion back toward the box is allowed). **Box values in `safety.yaml` are placeholders** |
| Engage check | after any `HOLD`/`ESTOP`, the first target must be within `max_start_error` (0.2 rad, hands 2.0) of the current output, otherwise the group stays still |
| Re-sync while held | if the measured position differs from the held output by more than `resync_threshold` (0.05 rad), the output follows it (robot moved by another controller or sagged) |
| Start-up | outputs start from the measured `/joint_states`, so activation never moves the robot |
| Hardware fault | stale `/joint_states` (> 100 ms) for a group -> that group is frozen and reported in `faulted_groups`; other groups continue |

Controller-level changes for P3: one `JointStateBroadcaster` per hardware component (a failing hand no longer stops the arm states);
`bringup.launch.py mode:=teleop` activates the forward controllers and starts the safety monitor.

The software e-stop is a controlled stop (hold position). It does not replace the hardware e-stop that cuts motor power.

### P3.2 Run

```bash
ros2 launch openarm_o6_bringup bringup.launch.py mode:=teleop          # + use_mock_hardware:=false on the real robot
ros2 topic echo /teleop/safety_state
ros2 topic pub --once /emergency_stop std_msgs/msg/Bool "{data: true}"   # e-stop
ros2 topic pub --once /emergency_stop std_msgs/msg/Bool "{data: false}"
ros2 service call /safety_monitor/reset std_srvs/srv/Trigger
```

### P3.3 Test report (mock hardware, 2026-11-27)

Acceptance test `ros2 run teleop_safety safety_test.py` (left arm, actions streamed at 100 Hz like retargeting;
timing events are triggered while the output is still moving):

| Test | Result | Detail |
|---|---|---|
| Command timeout -> hold | PASS | n=20, stop after last command: max 80.3 ms, mean 80.1 ms (requirement 100 ms), stopped short of target 20/20 |
| E-stop | PASS | n=100, effective 100/100 (no output change while commands keep streaming), latency max 0.4 ms, mean 0.1 ms |
| E-stop latch | PASS | reset refused while pressed; reset after release OK |
| Deadman release -> hold | PASS | n=10, max 10.0 ms (one 100 Hz action period) |
| Soft position limit | PASS | joint7 target 2.5 -> output 1.5508 rad (1.5708 - 0.02) |
| Velocity limit | PASS | 2.5 rad step -> 0.980 rad/s (limit 1.0) |
| Refuse far start target | PASS | 0.5 rad jump after hold: no motion, reason "target too far from current position" |

Additional checks:

| Check | Result |
|---|---|
| Unit tests (`colcon test --packages-select teleop_safety`) | pass |
| Workspace box (left box z max set to 0.30 m, tip starts at z 0.261) | joint4 sweep stops with the tip at z 0.300, `limited_groups=[left_arm]` |
| Fault isolation (fake O6, right hand killed) | arms and left hand `/joint_states` continue at ~500 Hz; `faulted_groups=[right_hand]`; right hand broadcaster/controllers deactivated by ros2_control |
| Outputs | 500 Hz on each command topic |

Latencies are measured at the safety monitor output (ROS topic). Robot-side stopping distance depends on the
motor controllers and must be measured on the real arms (P3 on hardware).

### P3.4 Pending (needs hardware)

- Measure the workspace box on the real cell and update `safety.yaml`.
- Hardware e-stop button: wiring (motor power cut) and a ROS input (e.g. USB/GPIO -> `/emergency_stop`).
- Repeat the acceptance test on the real arms and measure stopping distance/time.
- Decide whether a hand fault should hold the whole system (currently only the faulted group is held).

---

## P4 Teleoperation (simulated operator inputs)

Input devices are not available yet. The chain is built and tested with a simulated operator; the device
bridges are written against the vendor SDKs and still have to be verified.

Operator setup (decided): **Pico Motion Trackers strapped to the wrists / glove backs** give the wrist poses,
Manus gloves give the fingers (hands stay free), the headset gives the head pose, and a **foot pedal** is the
deadman / clutch (`/teleop/deadman`).

### P4.1 Packages

| Package | Runs in | Content |
|---|---|---|
| `teleop_msgs` | both | + `HandSkeleton` (glove joint names and angles) |
| `teleop_retargeting` | LXD `teleop` | `retarget_node` (arm IK + clutch, O6 finger map), `fake_operator`, `latency_probe`, `config/retarget.yaml`, `config/hand_map.yaml` |
| `pico_bridge` | LXD `teleop` | `pico_bridge_node` (XRoboToolkit Python SDK -> poses), `xr_frames.py` (OpenXR / Unity -> ROS frame conversion) |
| `openarm_o6_bringup` | host | + `go_ready.py`: move both arms to a ready pose with the trajectory controllers, then restore the forward controllers |
| `teleop_safety` | host | + `resync_threshold`: while a group is held, its output follows the measured position if the robot was moved by something else (controller switch, sag), so switching back never jumps; + per-group `max_start_error` (hands 2.0 rad) |

Topics:

| Topic | Type | From |
|---|---|---|
| `/pico/head_pose`, `/pico/{left,right}_hand_pose` | `geometry_msgs/PoseStamped` (frame `pico_world`, ROS axes) | `pico_bridge` (wrist = motion tracker) |
| `/manus/{left,right}_hand` | `teleop_msgs/HandSkeleton` (Manus ergonomics, rad) | `manus_bridge` (to do) |
| `/teleop/deadman` | `std_msgs/Bool`, published continuously (>= 50 Hz) | foot pedal node (to do) |
| `/teleop_action` | `teleop_msgs/TeleopAction`, 100 Hz | `retarget_node` |

### P4.2 Retargeting

- **Arms (clutch-relative)**: when the deadman is pressed, the current operator wrist pose and the robot hand pose
  (`{l,r}h_hand_base_link`, FK of the measured joints) are anchored. While pressed, the operator's motion since
  the anchor (rotated by the operator-to-robot yaw, translation scaled by `translation_scale`) is applied to the
  robot anchor. Releasing and re-pressing re-anchors, so the tracker mounting offset does not need calibration.
- **IK**: Pinocchio damped least squares on a reduced 7-joint model per arm, 20 iterations max, position + 0.3 x
  orientation weight, null-space pull to mid-range, limits shrunk by 0.03 rad (inside the safety soft limits).
- **Yaw calibration**: `ros2 service call /retarget_node/calibrate std_srvs/srv/Trigger` with the operator facing
  the robot's forward direction (uses the head yaw).
- **Hands**: each O6 joint = linear map of the mean of its glove inputs ([`hand_map.yaml`](../ros2_ws/src/teleop/teleop_retargeting/config/hand_map.yaml)).
  Per-operator calibration: hold the hand open -> `~/calibrate_hands_open`, make a fist -> `~/calibrate_hands_closed`.
- **Frame conversion** (`pico_bridge`): `input_convention:=openxr` (right-handed, y up, -z forward) or `unity`
  (left-handed); unit-tested against the basis change. Which one XRoboToolkit delivers must be checked on the headset.

### P4.3 Build and run

```bash
# Host (P2 workspace): builds teleop_* as well
bash system_config/scripts/p2_setup_ws.sh
# LXD teleop container: copies teleop_msgs / teleop_retargeting / pico_bridge, rosdep (pinocchio), colcon, snapshot p4-teleop
sudo bash system_config/scripts/p4_setup_teleop_lxd.sh

# Run (mock hardware)
ros2 launch openarm_o6_bringup bringup.launch.py mode:=teleop          # host
ros2 run openarm_o6_bringup go_ready.py                                  # host; deadman released
sudo lxc exec teleop -- bash -c 'source /root/teleop_ws/install/setup.bash; ros2 launch teleop_retargeting teleop.launch.py fake_operator:=true'
```

The fake operator moves both wrists on 5 cm circles (y-z plane, 4 s period) with +-0.3 rad roll, opens/closes the
fingers and keeps the deadman pressed.

### P4.4 Verification (mock hardware, simulated operator, 2026-11-27)

| Check | Result |
|---|---|
| Unit tests | `teleop_retargeting` 5 (hand map, calibration, relative mapping, IK reaches 50 random targets < 1 mm, IK limits), `pico_bridge` 3 (OpenXR/Unity conversion) - pass |
| Tracking, retargeting on host | both hand frames trace the 5 cm circle: range x/y/z = 0.001 / 0.100 / 0.100 m; safety `ACTIVE`, arms not limited |
| Tracking, retargeting in LXD `teleop` | same result (0.001 / 0.100 / 0.100 m) across the container boundary |
| Fingers | O6 joints follow the simulated glove (e.g. `rh_index_mcp_pitch` 0.5 -> 1.2 rad) |
| Latency, probe on host -> retargeting in LXD -> safety + mock hardware on host (n=30) | `/teleop_action` 13.6 ms mean / 16.1 max; safety output 14.4 / 16.9; `/joint_states` 17.6 / 20.2 |
| Latency, all on host (n=30) | 16.2 / 20.1 / 20.1 ms (action / safety / joint_states) |
| Input jitter across lxdbr0 | `/pico/left_hand_pose` and `/teleop/deadman` 90 Hz, max gap 12 ms |
| P3 acceptance test after the safety changes | all 7 tests pass |

The in-PTL part uses ~20 ms of the 100 ms end-to-end budget (mostly the 100 Hz retargeting tick and the
500 Hz safety cycle). The rest is Pico tracking + Wi-Fi + PC Service and the real motors.

### P4.5 To do with hardware

| Device | Check |
|---|---|
| Pico 4 Ultra + 2 Motion Trackers | Install XRoboToolkit (headset app + PC Service on PTL, `pip install xrobotoolkit-sdk` in LXD `teleop`); confirm the motion tracker API names and serial-number mapping in `pico_bridge_node`; confirm `input_convention`; measure rate/jitter over Wi-Fi 6E |
| Foot pedal | Pick a USB pedal; node publishing `/teleop/deadman` at >= 50 Hz; USB passthrough into LXD `teleop` |
| Manus | `manus_bridge` with the Manus Linux SDK (ergonomics -> `HandSkeleton`, deg -> rad); dongle passthrough (P1 profile TODO); per-operator calibration |
| Robot | `translation_scale`, ready pose, workspace box, IK tracking on the real arms |
| End to end | latency < 100 ms (slow-motion video of operator and robot), pick-and-place |

---

## Migrating to a new PTL

Everything on the host is reproducible from this repo; LXD containers and `/data` can be copied over instead of rebuilt.

### What moves how

| Item | Method |
|---|---|
| P0 platform (proxy, apt, Intel Robotics AI Suite) | `p0_setup_platform.sh` (re-run safe; uses `-resume` if a previous installer state exists) |
| P1 DDS config, LXD, profiles, containers | `p1_setup_lxd.sh` (re-run safe) |
| P2 workspace, realtime limits | `p2_setup_ws.sh` (re-run safe; upstream versions pinned in `.repos`) |
| P4 teleop packages in LXD `teleop` | `p4_setup_teleop_lxd.sh` (re-run safe; rebuilds from a fresh copy) |
| LXD containers with their state | `lxd_backup.sh export` on the old PTL, `lxd_backup.sh import` on the new one (optional; otherwise P1 rebuilds them) |
| `/data` (recordings) | `rsync -aP old-ptl:/data/ /data/` or via NAS |
| CAN names | Same adapters: copy `/etc/udev/rules.d/90-can.rules` and `/etc/systemd/network/10-*.network`; new adapters: run `can_setup.sh` |
| RT kernel, BIOS settings | Not scripted yet (added when the RT kernel is installed) |
| Not migrated | SSH keys, passwordless sudo, hostname/IP |

### Steps

```bash
# Old PTL (optional)
sudo bash ~/intel-teleop-data-collection/system_config/scripts/lxd_backup.sh export /data/backup/lxd

# New PTL (Ubuntu 24.04 installed, user with sudo)
sudo apt-get install -y git
git clone https://github.com/yanghc18/intel-teleop-data-collection.git ~/intel-teleop-data-collection
cd ~/intel-teleop-data-collection
PROXY=<PROXY> NO_PROXY_EXTRA=<LOCAL_SUBNETS> bash system_config/scripts/setup_ptl.sh   # omit PROXY outside the corporate network
# after a failure: fix, then  bash system_config/scripts/setup_ptl.sh --from p1   (or p2, p4)
# re-login (render, lxd, realtime groups)
sudo bash system_config/scripts/can_setup.sh                                          # plug in arm_r, arm_l, hand_r, hand_l
sudo bash system_config/scripts/lxd_backup.sh import <dir with the exported tar.gz>   # optional
```

`setup_ptl.sh` writes one log per step (`~/setup_p0.log`, `~/setup_p1.log`, `~/setup_p2.log`, `~/setup_p4.log`).
Validated on the current PTL with `--from p2` (P0/P1 already done there); a full run on a clean machine is still to be done.

---

## Pitfalls

| Symptom | Cause / Fix |
|---|---|
| No internet on PTL | Corporate proxy required; see P0.1 |
| Installer TUI hangs over SSH | Use `-auto -profile base -distro jazzy`; `robotics-installer -h` also opens the TUI |
| `pkill -f robotics-installer` kills your own SSH session | The pattern matches the SSH command line; use `pgrep -a` first and kill by PID |
| `pgrep -f <name>` wait loop over SSH never ends | It matches its own command line; use `pgrep -f '[n]ame'` |
| Scripts fail with `$'\r': command not found` | Files edited on Windows; run `sed -i 's/\r$//'` on them |
| `Permission denied` running `./system_config/scripts/*.sh` | Exec bit lost when files are copied/uploaded; `chmod +x system_config/scripts/*.sh` or run with `bash` |
| Long jobs die when SSH drops | Run with `nohup ... &` and log to a file |
| Host `/data` shows `nobody:nogroup` in container and is read-only | Unprivileged container UID mapping; add `shift: "true"` to the disk device (idmapped mount) |
| `lxc restart` hangs | Use `lxc restart <c> --force` |
| Script piped via `bash -s` stops after an `lxc exec` line | `lxc exec` consumes stdin; add `< /dev/null` |
| First DDS echo after starting a talker gets nothing | Discovery takes a few seconds; wait ~4 s before echo |
| `colcon build` fails on `linkerhand_O30i_right.urdf` (catkin not found) | colcon scans `third_party/`; add `third_party/COLCON_IGNORE` |
| `rosdep install` fails with "does not follow naming conventions" | Keep `linkerhand-urdf` outside `src/` |
| URDF parse error: material not unique | Both O6 URDFs define `silver`/`BlackAccent`; prefixed with `lh_`/`rh_` at build time |
| `Could not enable FIFO RT scheduling policy` | User not in `realtime` group / no rtprio limit; re-login after `p2_setup_ws.sh` and restart all ROS processes |
| ROS env missing in `ssh host "..."` commands | `.bashrc` returns early for non-interactive shells; export `ROS_DOMAIN_ID`, `RMW_IMPLEMENTATION`, `CYCLONEDDS_URI` explicitly |
| ros2_control loads the wrong plugins / "nodes share an exact name" | An orphaned `robot_state_publisher` from a killed launch still publishes the old `/robot_description`; kill leftover `robot_state_publisher`, `ros2_control_node`, `spawner` before relaunching |
| Latency probe shows missing samples / 400 ms outliers | A second operator source is still publishing (orphaned `fake_operator` in the container); check `pgrep -fa fake_operator` on host and in LXD |
| `ros2 run <pkg> <script>.py`: "No executable found" | The script lost its exec bit (copied from Windows) and `--symlink-install` links to the source; `chmod +x` the script |
| Robot jumps when switching from trajectory back to forward controllers | Fixed by `resync_threshold` in the safety monitor; still release the deadman before running `go_ready.py` |
