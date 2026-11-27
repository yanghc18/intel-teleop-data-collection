# Intel Robotics AI Suite Teleoperation & Data Collection System Design Request (Enhanced Version)

> The goal of this document is to have AI directly produce content close to a formal Architecture Design Document (ADD), System Design Specification (SDS), and Deployment Guide, rather than conceptual suggestions only.

## System Background

Analyze from the perspective of a Robotics System Architect, ROS2 Architect, and Edge AI Architect.

The goal is to build a Teleoperation, Data Collection, Imitation Learning, and VLA Dataset Generation platform centered on the Intel Platform.

## Hardware Platform

- Intel PTL 368H
- Ubuntu 24.04 LTS
- PREEMPT_RT Kernel
- Intel iGPU/NPU
- NVMe SSD
- Intel I226 Ethernet

## Software Platform

- Intel Robotics AI Suite
- ROS2 Jazzy
- OpenVINO
- ros2_control

## Robot Components

### Camera
- RealSense D435i on head
- Two RealSense D405 on hands

### Manipulator
- OpenARM 2.0
- Linker Bot O6
- USB-CAN
- OpenARM SDK
- Linker Bot SDK
- ROS2 Driver

### XR Device
- Pico 4 Ultra

### Hands Motion Capture
- Manus Gloves

## Target Workflow

Pico4 + Manus
→ Teleoperation
→ OpenARM + Linker O6
→ Multi-modal Data Collection
→ Demonstration Dataset

---

# Required Outputs

## 1. System Architecture

Provide:
- Overall Architecture Diagram
- Layered Architecture Diagram
- Runtime Architecture Diagram
- Data Flow Diagram
- Control Flow Diagram

## 2. Container Strategy Analysis

Compare:
- Docker
- LXD
- Hybrid (Host + LXD)

Analyze:
- Realtime Performance
- CAN Access
- USB Access
- GPU Access
- DDS Discovery
- Security
- Isolation
- Maintenance Cost
- Intel Robotics AI Suite Compatibility

Give a single recommended solution.

## 3. Component Deployment Matrix

Output a table:

| Component | Host | LXD | Docker | Reason |
|---|---|---|---|---|

Analyze:
- OpenARM SDK
- SocketCAN
- OpenARM Driver
- Linker Driver
- ros2_control
- MoveIt2
- RealSense
- OpenVINO
- VLA Runtime
- rosbag2

## 4. ROS2 Package Design

List all required packages, including:
- Package Name
- Node Name
- Interface
- Message Type
- Update Rate
- Responsibility

## 5. Teleoperation Pipeline

Describe:
- Pico4 Tracking
- Manus Tracking
- Robot Command Generation

List which modules run at which frequencies.

## 6. Data Collection Architecture

Collect:
- RGB
- Depth
- Joint States
- Base States
- End Effector Pose
- TF Tree
- Operator Actions
- Hand Skeleton

Analyze:
- rosbag2
- LeRobot Dataset
- OpenX Dataset
- HDF5

Recommend the official data format.

## 7. ROS2 Topic / Interface Matrix

Generate a complete table:

| Topic | Msg Type | Publisher | Subscriber | Rate | QoS |
|---|---|---|---|---|---|

Cover at least:
- /joint_states
- /tf
- /tf_static
- /cmd_vel
- /arm_controller
- /gripper_controller
- /manus_hand
- /pico_pose
- /teleop_action
- /camera/color
- /camera/depth
- /robot_state

And add any missing topics.

---

## Final Requirement

Finally, directly provide:

1. Final architecture diagram
2. Final deployment table
3. Final network topology
4. Final container solution
5. Final ROS2 package tree
6. Implementation steps
7. Rationale for recommendation
