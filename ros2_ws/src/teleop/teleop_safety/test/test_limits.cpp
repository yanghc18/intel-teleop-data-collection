#include <gtest/gtest.h>

#include <vector>

#include "teleop_safety/limits.hpp"

using teleop_safety::distance_to_box;
using teleop_safety::limit_step;

TEST(Limits, PositionClamp)
{
  std::vector<double> out{0.0};
  EXPECT_TRUE(limit_step(out, {5.0}, {-1.0}, {1.0}, {100.0}, 1.0));
  EXPECT_DOUBLE_EQ(out[0], 1.0);
}

TEST(Limits, VelocityLimit)
{
  std::vector<double> out{0.0, 0.0};
  EXPECT_TRUE(limit_step(out, {1.0, -1.0}, {-2.0, -2.0}, {2.0, 2.0}, {1.0, 0.5}, 0.002));
  EXPECT_DOUBLE_EQ(out[0], 0.002);
  EXPECT_DOUBLE_EQ(out[1], -0.001);
}

TEST(Limits, NoLimitWhenReachable)
{
  std::vector<double> out{0.0};
  EXPECT_FALSE(limit_step(out, {0.001}, {-1.0}, {1.0}, {1.0}, 0.002));
  EXPECT_DOUBLE_EQ(out[0], 0.001);
}

TEST(Limits, DistanceToBox)
{
  EXPECT_DOUBLE_EQ(distance_to_box({0.5, 0.5, 0.5}, {0, 0, 0}, {1, 1, 1}), 0.0);
  EXPECT_DOUBLE_EQ(distance_to_box({2.0, 0.5, 0.5}, {0, 0, 0}, {1, 1, 1}), 1.0);
  EXPECT_DOUBLE_EQ(distance_to_box({-3.0, -4.0, 0.5}, {0, 0, 0}, {1, 1, 1}), 5.0);
}
