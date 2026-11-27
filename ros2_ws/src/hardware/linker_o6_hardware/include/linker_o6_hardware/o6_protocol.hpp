// Linker Bot O6 CAN protocol, ported from linker-bot/linkerhand-ros2-sdk
// (LinkerHand/core/can/linker_hand_o6_can.py, LinkerHand/utils/mapping.py).
#pragma once

#include <linux/can.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <string_view>

namespace linker_o6_hardware::protocol
{

// Frame layout: standard 11-bit ID = hand ID, data[0] = command, data[1..6] = one byte per joint.
constexpr uint8_t kCmdPosition = 0x01;  // 6 bytes: set target; no payload: request current position
constexpr uint8_t kCmdTorque = 0x02;
constexpr uint8_t kCmdSpeed = 0x05;

constexpr uint16_t kLeftHandId = 0x28;
constexpr uint16_t kRightHandId = 0x27;

constexpr std::size_t kNumJoints = 6;

// Byte order on the bus (SDK: thumb flex, thumb abduction, index, middle, ring, little).
constexpr std::array<std::string_view, kNumJoints> kJointOrder = {
  "thumb_cmc_pitch", "thumb_cmc_yaw", "index_mcp_pitch",
  "middle_mcp_pitch", "ring_mcp_pitch", "pinky_mcp_pitch"};

// SDK mapping (direction -1): raw 255 = 0 rad (open), raw 0 = max_rad (closed).
inline uint8_t rad_to_raw(double rad, double max_rad)
{
  const double q = std::clamp(rad, 0.0, max_rad);
  return static_cast<uint8_t>(std::lround(255.0 * (1.0 - q / max_rad)));
}

inline double raw_to_rad(uint8_t raw, double max_rad)
{
  return (255.0 - raw) / 255.0 * max_rad;
}

inline can_frame make_frame(uint16_t can_id, uint8_t cmd, const uint8_t * payload, std::size_t len)
{
  can_frame f{};
  f.can_id = can_id;
  f.can_dlc = static_cast<uint8_t>(1 + std::min<std::size_t>(len, 7));
  f.data[0] = cmd;
  if (len > 0) {
    std::memcpy(&f.data[1], payload, f.can_dlc - 1);
  }
  return f;
}

// True if the frame is a 6-joint position report from this hand.
inline bool parse_position(const can_frame & f, uint16_t can_id, std::array<uint8_t, kNumJoints> & out)
{
  if ((f.can_id & CAN_EFF_FLAG) || (f.can_id & CAN_SFF_MASK) != can_id ||
    f.can_dlc != 1 + kNumJoints || f.data[0] != kCmdPosition)
  {
    return false;
  }
  std::memcpy(out.data(), &f.data[1], kNumJoints);
  return true;
}

}  // namespace linker_o6_hardware::protocol
