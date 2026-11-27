# intel-teleop-data-collection

Teleoperation and multi-modal data collection platform built on Intel PTL + Intel Robotics AI Suite.

**Workflow:** Pico 4 Ultra + Manus Gloves → Teleoperation → OpenARM 2.0 + Linker Bot O6 → Multi-modal Data Collection → Demonstration Dataset (LeRobot) for Imitation Learning / VLA.

## Platform

| Item | Spec |
|---|---|
| Compute | Intel PTL 368H, Ubuntu 24.04 LTS, PREEMPT_RT, iGPU/NPU, NVMe, I226 |
| Software | ROS2 Jazzy, ros2_control, MoveIt2, OpenVINO, Intel Robotics AI Suite |
| Arms | OpenARM 2.0 x2, Anvil Robotics edition ([anvil-robotics/openarm](https://github.com/anvil-robotics/openarm)), classic CAN 1 Mbps |
| Hands | Linker Bot O6 x2 (CAN) |
| XR | Pico 4 Ultra (head) + 2 Pico Motion Trackers (wrists); deadman / clutch from the keyboard (foot pedal optional) |
| Hand mocap | Manus Gloves (Linux SDK) |
| Cameras | RealSense D435i (head), RealSense D405 x2 (wrists) |
| Containers | LXD Hybrid (Host + LXD) |

## Repository Layout

| Path | Content |
|---|---|
| [docs/](docs) | Plan, setup steps and test reports |
| [system_config/](system_config) | Cyclone DDS, LXD preseed/profiles, setup scripts (new-PTL provisioning, RT kernel, LXD, CAN, ROS 2 workspaces) |
| [ros2_ws/](ros2_ws) | ROS 2 workspace: own packages in `src/`, upstream sources pinned in `upstream.repos` / `third_party.repos` |

ROS 2 packages:

| Package | Runs in | Purpose |
|---|---|---|
| `openarm_o6_description` | host | URDF: bimanual OpenARM 2.0 + Linker O6 hands |
| `openarm_o6_bringup` | host | ros2_control bringup (mock or real hardware; `mode:=manual` / `mode:=teleop`), `go_ready.py` |
| `linker_o6_hardware` | host | ros2_control plugin for the O6 over SocketCAN, plus a CAN simulator |
| `teleop_safety` | host | 500 Hz safety monitor: e-stop, deadman, command timeout, joint/velocity/workspace limits |
| `teleop_msgs` | host + LXD | `TeleopAction`, `SafetyState`, `HandSkeleton` |
| `teleop_retargeting` | LXD `teleop` | Wrist poses -> arm IK (clutch-relative), glove -> O6 fingers; simulated operator and latency probe |
| `pico_bridge` | LXD `teleop` | Pico 4 Ultra / Motion Trackers via XRoboToolkit -> ROS poses |

## Documents

- [docs/plan.md](docs/plan.md) - Implementation plan (architecture, deployment, ROS2 packages, topics, phases)
- [docs/setup_steps.md](docs/setup_steps.md) - Executed setup steps and test reports for P0-P4, new-PTL migration (with Dockerfile mapping)
- [docs/architecture_request.md](docs/architecture_request.md) - Original architecture design request

## Quick Start

New PTL (Ubuntu 24.04):

```bash
git clone https://github.com/yanghc18/intel-teleop-data-collection.git ~/intel-teleop-data-collection
cd ~/intel-teleop-data-collection
[PROXY=http://host:port] bash system_config/scripts/setup_ptl.sh   # P0 platform, P1 LXD, P2 workspace, P4 teleop container
bash system_config/scripts/p0b_setup_rt_kernel.sh                  # before real hardware: PREEMPT_RT kernel, then reboot
```

Run with mock hardware and a simulated operator:

```bash
source ros2_ws/install/setup.bash
ros2 launch openarm_o6_bringup bringup.launch.py mode:=teleop   # host: ros2_control + safety monitor
ros2 run openarm_o6_bringup go_ready.py                          # host: ready pose
sudo lxc exec teleop -- bash -c 'source /root/teleop_ws/install/setup.bash; ros2 launch teleop_retargeting teleop.launch.py fake_operator:=true'
```

## Status

| Phase | Description | Status |
|---|---|---|
| P0 | Platform setup (Intel Robotics AI Suite Getting Started) | Done; RT kernel scripted (`p0b_setup_rt_kernel.sh`), not installed yet |
| P1 | LXD containers and DDS networking | Done (USB passthrough pending devices) |
| P2 | Hardware drivers | Done with mock hardware and simulated O6 on vcan; real-hardware validation pending |
| P3 | Safety layer | Done with mock hardware (acceptance test passed); real-arm tests pending (hardware e-stop button optional) |
| P4 | Teleoperation (Pico + Manus) | Retargeting chain done with a simulated operator (in-PTL latency ~18 ms); XRoboToolkit SDK installed; device bridges pending hardware |
| P5 | Perception and recording (+ MuJoCo digital twin after hardware validation) | Not started |
| P6 | Dataset tools (MCAP to LeRobot) | Not started |
| P7 | AI closed loop (optional) | Not started |
| P8 | Documentation and delivery | Not started |

Currently only the PTL system is available; external devices are pending. Software integration proceeds with mock hardware first.
The PREEMPT_RT kernel will be installed before the real-hardware tests; P2-P4 with mock hardware do not require it.
