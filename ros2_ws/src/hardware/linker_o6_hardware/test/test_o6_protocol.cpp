#include <gtest/gtest.h>

#include <array>

#include "linker_o6_hardware/o6_protocol.hpp"

using namespace linker_o6_hardware::protocol;

TEST(O6Protocol, MappingMatchesSdk)
{
  // SDK arc_to_range: 0 rad -> 255 (open), max -> 0 (closed).
  EXPECT_EQ(rad_to_raw(0.0, 1.6), 255);
  EXPECT_EQ(rad_to_raw(1.6, 1.6), 0);
  EXPECT_EQ(rad_to_raw(0.8, 1.6), 128);
  EXPECT_EQ(rad_to_raw(-1.0, 1.6), 255);
  EXPECT_EQ(rad_to_raw(9.0, 1.6), 0);
  EXPECT_DOUBLE_EQ(raw_to_rad(255, 0.58), 0.0);
  EXPECT_DOUBLE_EQ(raw_to_rad(0, 0.58), 0.58);
  for (int raw = 0; raw <= 255; ++raw) {
    EXPECT_EQ(rad_to_raw(raw_to_rad(static_cast<uint8_t>(raw), 1.36), 1.36), raw);
  }
}

TEST(O6Protocol, FrameLayout)
{
  const std::array<uint8_t, kNumJoints> pos{1, 2, 3, 4, 5, 6};
  const can_frame set = make_frame(kRightHandId, kCmdPosition, pos.data(), pos.size());
  EXPECT_EQ(set.can_id, 0x27u);
  EXPECT_EQ(set.can_dlc, 7);
  EXPECT_EQ(set.data[0], 0x01);
  EXPECT_EQ(set.data[6], 6);

  const can_frame poll = make_frame(kLeftHandId, kCmdPosition, nullptr, 0);
  EXPECT_EQ(poll.can_id, 0x28u);
  EXPECT_EQ(poll.can_dlc, 1);
}

TEST(O6Protocol, ParsePosition)
{
  std::array<uint8_t, kNumJoints> out{};
  const std::array<uint8_t, kNumJoints> pos{200, 255, 254, 254, 254, 180};
  can_frame f = make_frame(kRightHandId, kCmdPosition, pos.data(), pos.size());
  ASSERT_TRUE(parse_position(f, kRightHandId, out));
  EXPECT_EQ(out, pos);

  EXPECT_FALSE(parse_position(f, kLeftHandId, out));          // other hand
  f.data[0] = kCmdSpeed;
  EXPECT_FALSE(parse_position(f, kRightHandId, out));         // other command
  const can_frame poll = make_frame(kRightHandId, kCmdPosition, nullptr, 0);
  EXPECT_FALSE(parse_position(poll, kRightHandId, out));      // request, not a report
}
