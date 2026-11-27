#pragma once

#include <array>
#include <chrono>
#include <cstdint>
#include <string>
#include <vector>

#include "hardware_interface/system_interface.hpp"
#include "hardware_interface/types/hardware_component_interface_params.hpp"
#include "linker_o6_hardware/o6_protocol.hpp"
#include "rclcpp_lifecycle/state.hpp"

namespace linker_o6_hardware
{

class LinkerO6System : public hardware_interface::SystemInterface
{
public:
  using CallbackReturn = hardware_interface::CallbackReturn;
  using Clock = std::chrono::steady_clock;

  CallbackReturn on_init(const hardware_interface::HardwareComponentInterfaceParams & params) override;
  CallbackReturn on_configure(const rclcpp_lifecycle::State & previous_state) override;
  CallbackReturn on_cleanup(const rclcpp_lifecycle::State & previous_state) override;
  CallbackReturn on_shutdown(const rclcpp_lifecycle::State & previous_state) override;
  CallbackReturn on_activate(const rclcpp_lifecycle::State & previous_state) override;

  hardware_interface::return_type read(const rclcpp::Time & time, const rclcpp::Duration & period) override;
  hardware_interface::return_type write(const rclcpp::Time & time, const rclcpp::Duration & period) override;

private:
  struct Joint
  {
    std::string name;
    std::size_t raw_index;  // byte position on the bus
    double max_rad;         // URDF upper limit
    bool has_velocity_state;
  };

  bool send(uint8_t cmd, const uint8_t * payload, std::size_t len);
  bool receive_state();  // drains the socket; true if a position report arrived
  void close_socket();

  std::vector<Joint> joints_;
  std::string can_interface_;
  uint16_t can_id_{0};
  uint8_t speed_{255};
  uint8_t torque_{255};
  Clock::duration command_period_{};
  Clock::duration state_period_{};
  Clock::duration state_timeout_{};
  int sock_{-1};

  std::array<uint8_t, protocol::kNumJoints> raw_state_{};
  std::array<uint8_t, protocol::kNumJoints> last_sent_{};
  std::vector<double> prev_position_;
  Clock::time_point last_rx_{};
  Clock::time_point prev_rx_{};
  Clock::time_point last_cmd_tx_{};
  Clock::time_point last_poll_{};
};

}  // namespace linker_o6_hardware
