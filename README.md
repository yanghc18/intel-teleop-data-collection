# intel-teleop-data-collection

Teleoperation and multi-modal data collection platform built on Intel PTL + Intel Robotics AI Suite.

**Workflow:** Pico 4 Ultra + Manus Gloves → Teleoperation → OpenARM 2.0 + Linker Bot O6 → Multi-modal Data Collection → Demonstration Dataset (LeRobot) for Imitation Learning / VLA.

## Platform

| Item | Spec |
|---|---|
| Compute | Intel PTL 368H, Ubuntu 24.04 LTS, PREEMPT_RT, iGPU/NPU, NVMe, I226 |
| Software | ROS2 Jazzy, ros2_control, MoveIt2, OpenVINO, Intel Robotics AI Suite |
| Arms | OpenARM 2.0 x2 (USB-CAN) |
| Hands | Linker Bot O6 x2 |
| XR | Pico 4 Ultra |
| Hand mocap | Manus Gloves (Linux SDK) |
| Cameras | RealSense D435i (head), RealSense D405 x2 (wrists) |
| Containers | LXD Hybrid (Host + LXD) |

## Documents

- [docs/plan.md](docs/plan.md) - Implementation plan (architecture, deployment, ROS2 packages, topics, phases)
- [docs/setup_steps.md](docs/setup_steps.md) - Executed setup steps for P0/P1 (with Dockerfile mapping)
- [docs/architecture_request.md](docs/architecture_request.md) - Original architecture design request
- [system_config/](system_config) - Cyclone DDS, LXD preseed/profiles, setup scripts

## Status

| Phase | Description | Status |
|---|---|---|
| P0 | Platform setup (Intel Robotics AI Suite Getting Started) | Done (RT kernel deferred) |
| P1 | LXD containers and DDS networking | Done (USB passthrough pending devices) |
| P2 | Hardware drivers (mock hardware until devices arrive) | Not started |
| P3 | Safety layer | Not started |
| P4 | Teleoperation (Pico + Manus) | Not started |
| P5 | Perception and recording | Not started |
| P6 | Dataset tools (MCAP to LeRobot) | Not started |
| P7 | AI closed loop (optional) | Not started |
| P8 | Documentation and delivery | Not started |

Currently only the PTL system is available; external devices are pending. Software integration proceeds with mock hardware first.
The PREEMPT_RT kernel will be installed later; P2-P4 with mock hardware do not require it.
