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
| XR | Pico 4 Ultra |
| Hand mocap | Manus Gloves (Linux SDK) |
| Cameras | RealSense D435i (head), RealSense D405 x2 (wrists) |
| Containers | LXD Hybrid (Host + LXD) |

## Repository Layout

| Path | Content |
|---|---|
| [docs/](docs) | Plan, setup steps and test reports |
| [system_config/](system_config) | Cyclone DDS, LXD preseed/profiles, setup scripts (LXD, CAN, ROS 2 workspace) |
| [ros2_ws/](ros2_ws) | ROS 2 workspace: own packages in `src/`, upstream sources pinned in `upstream.repos` / `third_party.repos` |

ROS 2 packages:

| Package | Purpose |
|---|---|
| `openarm_o6_description` | URDF: bimanual OpenARM 2.0 + Linker O6 hands |
| `openarm_o6_bringup` | ros2_control bringup (mock or real hardware; `mode:=manual` / `mode:=teleop`) |
| `linker_o6_hardware` | ros2_control plugin for the O6 over SocketCAN, plus a CAN simulator |
| `teleop_msgs` | `TeleopAction`, `SafetyState` |
| `teleop_safety` | 500 Hz safety monitor: e-stop, deadman, command timeout, joint/velocity/workspace limits |

## Documents

- [docs/plan.md](docs/plan.md) - Implementation plan (architecture, deployment, ROS2 packages, topics, phases)
- [docs/setup_steps.md](docs/setup_steps.md) - Executed setup steps and test reports for P0-P3 (with Dockerfile mapping)
- [docs/architecture_request.md](docs/architecture_request.md) - Original architecture design request

## Quick Start (mock hardware)

```bash
./system_config/scripts/p2_setup_ws.sh                        # build the workspace
source ros2_ws/install/setup.bash
ros2 launch openarm_o6_bringup bringup.launch.py              # manual jogging
ros2 launch openarm_o6_bringup bringup.launch.py mode:=teleop # safety monitor + streaming controllers
```

## Status

| Phase | Description | Status |
|---|---|---|
| P0 | Platform setup (Intel Robotics AI Suite Getting Started) | Done (RT kernel deferred) |
| P1 | LXD containers and DDS networking | Done (USB passthrough pending devices) |
| P2 | Hardware drivers | Done with mock hardware and simulated O6 on vcan; real-hardware validation pending |
| P3 | Safety layer | Done with mock hardware (acceptance test passed); hardware e-stop and real-arm tests pending |
| P4 | Teleoperation (Pico + Manus) | Not started |
| P5 | Perception and recording | Not started |
| P6 | Dataset tools (MCAP to LeRobot) | Not started |
| P7 | AI closed loop (optional) | Not started |
| P8 | Documentation and delivery | Not started |

Currently only the PTL system is available; external devices are pending. Software integration proceeds with mock hardware first.
The PREEMPT_RT kernel will be installed later; P2-P4 with mock hardware do not require it.
