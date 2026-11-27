#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <vector>

namespace teleop_safety
{

// Clamp target to [lower, upper] and move out toward it by at most vmax*dt per joint.
// Returns true if any joint was position- or velocity-limited.
inline bool limit_step(
  std::vector<double> & out, const std::vector<double> & target,
  const std::vector<double> & lower, const std::vector<double> & upper,
  const std::vector<double> & vmax, double dt)
{
  bool limited = false;
  for (std::size_t i = 0; i < out.size(); ++i) {
    const double t = std::clamp(target[i], lower[i], upper[i]);
    const double max_step = vmax[i] * dt;
    const double step = std::clamp(t - out[i], -max_step, max_step);
    limited |= (t != target[i]) || (step != t - out[i]);
    out[i] += step;
  }
  return limited;
}

inline double max_abs_diff(const std::vector<double> & a, const std::vector<double> & b)
{
  double m = 0.0;
  for (std::size_t i = 0; i < a.size(); ++i) {
    m = std::max(m, std::abs(a[i] - b[i]));
  }
  return m;
}

// Euclidean distance from p to an axis-aligned box (0 inside).
inline double distance_to_box(
  const std::array<double, 3> & p, const std::array<double, 3> & lo, const std::array<double, 3> & hi)
{
  double d2 = 0.0;
  for (std::size_t k = 0; k < 3; ++k) {
    const double d = std::max({lo[k] - p[k], 0.0, p[k] - hi[k]});
    d2 += d * d;
  }
  return std::sqrt(d2);
}

}  // namespace teleop_safety
