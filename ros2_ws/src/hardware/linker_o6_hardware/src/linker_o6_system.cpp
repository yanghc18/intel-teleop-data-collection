#include "linker_o6_hardware/linker_o6_system.hpp"

#include <fcntl.h>
#include <linux/can/raw.h>
#include <net/if.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstring>
#include <stdexcept>
#include <thread>

#include "hardware_interface/types/hardware_interface_type_values.hpp"
#include "pluginlib/class_list_macros.hpp"
#include "rclcpp/rclcpp.hpp"

namespace linker_o6_hardware
{
namespace
{
using hardware_interface::HW_IF_POSITION;
using hardware_interface::HW_IF_VELOCITY;

std::string param(const hardware_interface::HardwareInfo & info, const std::string & key, const std::string & def)
{
  const auto it = info.hardware_parameters.find(key);
  return it == info.hardware_parameters.end() ? def : it->second;
}

std::chrono::steady_clock::duration period_from_hz(double hz)
{
  return std::chrono::duration_cast<std::chrono::steady_clock::duration>(std::chrono::duration<double>(1.0 / hz));
}

uint8_t to_byte(const std::string & s)
{
  const long v = std::stol(s, nullptr, 0);
  if (v < 0 || v > 255) {
    throw std::out_of_range(s);
  }
  return static_cast<uint8_t>(v);
}
}  // namespace

hardware_interface::CallbackReturn LinkerO6System::on_init(
  const hardware_interface::HardwareComponentInterfaceParams & params)
{
  if (SystemInterface::on_init(params) != CallbackReturn::SUCCESS) {
    return CallbackReturn::ERROR;
  }

  try {
    can_interface_ = param(info_, "can_interface", "");
    const std::string hand_type = param(info_, "hand_type", "");
    if (can_interface_.empty() || (hand_type != "left" && hand_type != "right")) {
      RCLCPP_ERROR(get_logger(), "Parameters 'can_interface' and 'hand_type' (left|right) are required");
      return CallbackReturn::ERROR;
    }
    const uint16_t default_id = hand_type == "left" ? protocol::kLeftHandId : protocol::kRightHandId;
    can_id_ = static_cast<uint16_t>(std::stoul(param(info_, "can_id", std::to_string(default_id)), nullptr, 0));
    speed_ = to_byte(param(info_, "speed", "255"));
    torque_ = to_byte(param(info_, "torque", "255"));
    // SDK reference node runs at 60 Hz; real limit to be measured on hardware.
    command_period_ = period_from_hz(std::stod(param(info_, "command_rate_hz", "60")));
    state_period_ = period_from_hz(std::stod(param(info_, "state_rate_hz", "60")));
    state_timeout_ = std::chrono::milliseconds(std::stol(param(info_, "state_timeout_ms", "200")));
  } catch (const std::exception & e) {
    RCLCPP_ERROR(get_logger(), "Invalid hardware parameter: %s", e.what());
    return CallbackReturn::ERROR;
  }

  if (info_.joints.size() != protocol::kNumJoints) {
    RCLCPP_ERROR(get_logger(), "Expected %zu joints, got %zu", protocol::kNumJoints, info_.joints.size());
    return CallbackReturn::ERROR;
  }

  std::array<bool, protocol::kNumJoints> used{};
  for (const auto & j : info_.joints) {
    const auto it = std::find_if(
      protocol::kJointOrder.begin(), protocol::kJointOrder.end(),
      [&j](std::string_view suffix) {
        return j.name.size() >= suffix.size() &&
               j.name.compare(j.name.size() - suffix.size(), suffix.size(), suffix) == 0;
      });
    if (it == protocol::kJointOrder.end()) {
      RCLCPP_ERROR(get_logger(), "Joint '%s' does not match any O6 joint", j.name.c_str());
      return CallbackReturn::ERROR;
    }
    const auto idx = static_cast<std::size_t>(std::distance(protocol::kJointOrder.begin(), it));
    if (used[idx]) {
      RCLCPP_ERROR(get_logger(), "Duplicate O6 joint '%s'", j.name.c_str());
      return CallbackReturn::ERROR;
    }
    used[idx] = true;

    const auto lim = info_.limits.find(j.name);
    if (lim == info_.limits.end() || !lim->second.has_position_limits || lim->second.max_position <= 0.0) {
      RCLCPP_ERROR(get_logger(), "Joint '%s' needs a positive URDF upper limit", j.name.c_str());
      return CallbackReturn::ERROR;
    }
    if (j.command_interfaces.size() != 1 || j.command_interfaces[0].name != HW_IF_POSITION) {
      RCLCPP_ERROR(get_logger(), "Joint '%s' must have exactly one 'position' command interface", j.name.c_str());
      return CallbackReturn::ERROR;
    }
    const bool has_vel = std::any_of(
      j.state_interfaces.begin(), j.state_interfaces.end(),
      [](const auto & s) {return s.name == HW_IF_VELOCITY;});
    joints_.push_back({j.name, idx, lim->second.max_position, has_vel});
  }
  prev_position_.assign(joints_.size(), 0.0);

  RCLCPP_INFO(
    get_logger(), "O6 on %s, CAN ID 0x%02X, speed %u, torque %u",
    can_interface_.c_str(), can_id_, speed_, torque_);
  return CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn LinkerO6System::on_configure(const rclcpp_lifecycle::State &)
{
  sock_ = ::socket(PF_CAN, SOCK_RAW, CAN_RAW);
  if (sock_ < 0) {
    RCLCPP_ERROR(get_logger(), "socket(): %s", std::strerror(errno));
    return CallbackReturn::ERROR;
  }
  const unsigned int ifindex = if_nametoindex(can_interface_.c_str());
  if (ifindex == 0) {
    RCLCPP_ERROR(get_logger(), "CAN interface '%s' not found", can_interface_.c_str());
    close_socket();
    return CallbackReturn::ERROR;
  }
  can_filter filter{can_id_, CAN_SFF_MASK | CAN_EFF_FLAG | CAN_RTR_FLAG};
  ::setsockopt(sock_, SOL_CAN_RAW, CAN_RAW_FILTER, &filter, sizeof(filter));
  sockaddr_can addr{};
  addr.can_family = AF_CAN;
  addr.can_ifindex = static_cast<int>(ifindex);
  if (::bind(sock_, reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) < 0) {
    RCLCPP_ERROR(get_logger(), "bind(%s): %s", can_interface_.c_str(), std::strerror(errno));
    close_socket();
    return CallbackReturn::ERROR;
  }
  ::fcntl(sock_, F_SETFL, ::fcntl(sock_, F_GETFL) | O_NONBLOCK);
  return CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn LinkerO6System::on_cleanup(const rclcpp_lifecycle::State &)
{
  close_socket();
  return CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn LinkerO6System::on_shutdown(const rclcpp_lifecycle::State &)
{
  close_socket();
  return CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn LinkerO6System::on_activate(const rclcpp_lifecycle::State &)
{
  receive_state();  // discard stale frames

  const std::array<uint8_t, protocol::kNumJoints> speed{speed_, speed_, speed_, speed_, speed_, speed_};
  const std::array<uint8_t, protocol::kNumJoints> torque{torque_, torque_, torque_, torque_, torque_, torque_};
  if (!send(protocol::kCmdSpeed, speed.data(), speed.size()) ||
    !send(protocol::kCmdTorque, torque.data(), torque.size()))
  {
    return CallbackReturn::ERROR;
  }

  // Start from the measured pose so activation never moves the hand.
  bool got_state = false;
  for (int attempt = 0; attempt < 10 && !got_state; ++attempt) {
    send(protocol::kCmdPosition, nullptr, 0);
    for (int i = 0; i < 10 && !got_state; ++i) {
      std::this_thread::sleep_for(std::chrono::milliseconds(5));
      got_state = receive_state();
    }
  }
  if (!got_state) {
    RCLCPP_ERROR(get_logger(), "No position report from O6 (ID 0x%02X) on %s", can_id_, can_interface_.c_str());
    return CallbackReturn::ERROR;
  }

  for (std::size_t i = 0; i < joints_.size(); ++i) {
    const auto & j = joints_[i];
    const double q = protocol::raw_to_rad(raw_state_[j.raw_index], j.max_rad);
    set_state(j.name + "/" + HW_IF_POSITION, q);
    if (j.has_velocity_state) {
      set_state(j.name + "/" + HW_IF_VELOCITY, 0.0);
    }
    set_command(j.name + "/" + HW_IF_POSITION, q);
    prev_position_[i] = q;
  }
  last_sent_ = raw_state_;
  prev_rx_ = last_rx_;
  last_cmd_tx_ = last_poll_ = Clock::now();
  return CallbackReturn::SUCCESS;
}

hardware_interface::return_type LinkerO6System::read(const rclcpp::Time &, const rclcpp::Duration &)
{
  const auto now = Clock::now();
  if (receive_state()) {
    const double dt = std::chrono::duration<double>(last_rx_ - prev_rx_).count();
    prev_rx_ = last_rx_;
    for (std::size_t i = 0; i < joints_.size(); ++i) {
      const auto & j = joints_[i];
      const double q = protocol::raw_to_rad(raw_state_[j.raw_index], j.max_rad);
      set_state(j.name + "/" + HW_IF_POSITION, q);
      if (j.has_velocity_state) {
        set_state(j.name + "/" + HW_IF_VELOCITY, dt > 0.0 ? (q - prev_position_[i]) / dt : 0.0);
      }
      prev_position_[i] = q;
    }
  } else if (now - last_rx_ > state_timeout_) {
    RCLCPP_ERROR(
      get_logger(), "O6 on %s: no position report for %ld ms", can_interface_.c_str(),
      static_cast<long>(std::chrono::duration_cast<std::chrono::milliseconds>(now - last_rx_).count()));
    return hardware_interface::return_type::ERROR;
  }
  return hardware_interface::return_type::OK;
}

hardware_interface::return_type LinkerO6System::write(const rclcpp::Time &, const rclcpp::Duration &)
{
  const auto now = Clock::now();

  if (now - last_cmd_tx_ >= command_period_) {
    auto raw = last_sent_;
    for (const auto & j : joints_) {
      const double cmd = get_command<double>(j.name + "/" + HW_IF_POSITION);
      if (std::isfinite(cmd)) {
        raw[j.raw_index] = protocol::rad_to_raw(cmd, j.max_rad);
      }
    }
    if (raw != last_sent_) {
      if (!send(protocol::kCmdPosition, raw.data(), raw.size())) {
        return hardware_interface::return_type::ERROR;
      }
      last_sent_ = raw;
      last_cmd_tx_ = now;
    }
  }

  if (now - last_poll_ >= state_period_) {
    if (!send(protocol::kCmdPosition, nullptr, 0)) {
      return hardware_interface::return_type::ERROR;
    }
    last_poll_ = now;
  }
  return hardware_interface::return_type::OK;
}

bool LinkerO6System::send(uint8_t cmd, const uint8_t * payload, std::size_t len)
{
  const can_frame f = protocol::make_frame(can_id_, cmd, payload, len);
  if (::write(sock_, &f, sizeof(f)) != static_cast<ssize_t>(sizeof(f))) {
    // ENOBUFS = TX queue full (bus off / no ACK); treat as a lost frame, the state timeout catches a dead bus.
    if (errno == ENOBUFS || errno == EAGAIN) {
      return true;
    }
    RCLCPP_ERROR(get_logger(), "CAN write on %s: %s", can_interface_.c_str(), std::strerror(errno));
    return false;
  }
  return true;
}

bool LinkerO6System::receive_state()
{
  bool got = false;
  can_frame f{};
  while (::read(sock_, &f, sizeof(f)) == static_cast<ssize_t>(sizeof(f))) {
    if (protocol::parse_position(f, can_id_, raw_state_)) {
      got = true;
    }
  }
  if (got) {
    last_rx_ = Clock::now();
  }
  return got;
}

void LinkerO6System::close_socket()
{
  if (sock_ >= 0) {
    ::close(sock_);
    sock_ = -1;
  }
}

}  // namespace linker_o6_hardware

PLUGINLIB_EXPORT_CLASS(linker_o6_hardware::LinkerO6System, hardware_interface::SystemInterface)
