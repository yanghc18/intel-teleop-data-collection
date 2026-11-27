// Host-side safety layer: TeleopAction -> limited position commands for the forward controllers.
#include <array>
#include <chrono>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "kdl/chainfksolverpos_recursive.hpp"
#include "kdl_parser/kdl_parser.hpp"
#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/joint_state.hpp"
#include "std_msgs/msg/bool.hpp"
#include "std_msgs/msg/float64_multi_array.hpp"
#include "std_msgs/msg/string.hpp"
#include "std_srvs/srv/trigger.hpp"
#include "teleop_msgs/msg/safety_state.hpp"
#include "teleop_msgs/msg/teleop_action.hpp"
#include "teleop_safety/limits.hpp"
#include "urdf/model.h"

namespace teleop_safety
{

using teleop_msgs::msg::SafetyState;
using teleop_msgs::msg::TeleopAction;
using Float64MultiArray = std_msgs::msg::Float64MultiArray;
using SteadyClock = std::chrono::steady_clock;

class SafetyMonitor : public rclcpp::Node
{
public:
  SafetyMonitor()
  : Node("safety_monitor")
  {
    rate_hz_ = declare_parameter("rate_hz", 500.0);
    command_timeout_ = declare_parameter("command_timeout", 0.08);
    state_timeout_ = declare_parameter("state_timeout", 0.1);
    margin_ = declare_parameter("soft_limit_margin", 0.02);
    max_start_error_ = declare_parameter("max_start_error", 0.2);
    resync_threshold_ = declare_parameter("resync_threshold", 0.05);
    const auto names = declare_parameter("groups", std::vector<std::string>{});

    for (const auto & n : names) {
      Group g;
      g.name = n;
      g.joints = declare_parameter(n + ".joints", std::vector<std::string>{});
      g.max_velocity = declare_parameter(n + ".max_velocity", 0.5);
      g.max_start_error = declare_parameter(n + ".max_start_error", max_start_error_);
      g.ws_enabled = declare_parameter(n + ".workspace.enabled", false);
      g.ws_base = declare_parameter(n + ".workspace.base_link", std::string{});
      g.ws_tip = declare_parameter(n + ".workspace.tip_link", std::string{});
      const auto lo = declare_parameter(n + ".workspace.min", std::vector<double>{-1e3, -1e3, -1e3});
      const auto hi = declare_parameter(n + ".workspace.max", std::vector<double>{1e3, 1e3, 1e3});
      std::copy_n(lo.begin(), 3, g.ws_min.begin());
      std::copy_n(hi.begin(), 3, g.ws_max.begin());
      g.pub = create_publisher<Float64MultiArray>(
        declare_parameter(n + ".command_topic", "/" + n + "_controller/commands"), rclcpp::QoS(1));
      groups_.push_back(std::move(g));
    }

    state_pub_ = create_publisher<SafetyState>("/teleop/safety_state", rclcpp::QoS(1));
    description_sub_ = create_subscription<std_msgs::msg::String>(
      "/robot_description", rclcpp::QoS(1).transient_local(),
      [this](std_msgs::msg::String::ConstSharedPtr msg) {on_description(msg->data);});
    joint_sub_ = create_subscription<sensor_msgs::msg::JointState>(
      "/joint_states", rclcpp::SensorDataQoS(),
      [this](sensor_msgs::msg::JointState::ConstSharedPtr msg) {
        const auto now = SteadyClock::now();
        for (std::size_t i = 0; i < msg->name.size() && i < msg->position.size(); ++i) {
          measured_[msg->name[i]] = {msg->position[i], now};
        }
      });
    action_sub_ = create_subscription<TeleopAction>(
      "/teleop_action", rclcpp::QoS(1).best_effort(),
      [this](TeleopAction::ConstSharedPtr msg) {
        action_ = *msg;
        action_time_ = SteadyClock::now();
      });
    estop_sub_ = create_subscription<std_msgs::msg::Bool>(
      "/emergency_stop", rclcpp::QoS(1).transient_local(),
      [this](std_msgs::msg::Bool::ConstSharedPtr msg) {
        estop_input_ = msg->data;
        if (msg->data) {
          estop_latched_ = true;
        }
      });
    reset_srv_ = create_service<std_srvs::srv::Trigger>(
      "~/reset",
      [this](std_srvs::srv::Trigger::Request::ConstSharedPtr,
      std_srvs::srv::Trigger::Response::SharedPtr res) {
        res->success = !estop_input_;
        res->message = estop_input_ ? "/emergency_stop is still true" : "e-stop cleared";
        if (res->success) {
          estop_latched_ = false;
        }
      });
  }

private:
  struct Group
  {
    std::string name;
    std::vector<std::string> joints;
    double max_velocity{0.5};
    double max_start_error{0.2};
    std::vector<double> lower, upper, vmax, out;
    bool initialized{false};
    bool engaged{false};
    rclcpp::Publisher<Float64MultiArray>::SharedPtr pub;

    bool ws_enabled{false};
    std::string ws_base, ws_tip;
    std::array<double, 3> ws_min{}, ws_max{};
    KDL::Chain chain;
    std::unique_ptr<KDL::ChainFkSolverPos_recursive> fk;
    std::vector<std::size_t> chain_to_group;  // chain joint i -> index in joints
  };

  void on_description(const std::string & xml)
  {
    if (timer_) {
      return;
    }
    urdf::Model model;
    KDL::Tree tree;
    if (!model.initString(xml) || !kdl_parser::treeFromString(xml, tree)) {
      RCLCPP_ERROR(get_logger(), "Failed to parse /robot_description");
      return;
    }
    for (auto & g : groups_) {
      for (const auto & jn : g.joints) {
        const auto j = model.getJoint(jn);
        if (!j || !j->limits) {
          RCLCPP_FATAL(get_logger(), "Group %s: joint '%s' has no URDF limits", g.name.c_str(), jn.c_str());
          rclcpp::shutdown();
          return;
        }
        g.lower.push_back(j->limits->lower + margin_);
        g.upper.push_back(j->limits->upper - margin_);
        g.vmax.push_back(std::min(j->limits->velocity, g.max_velocity));
      }
      if (g.ws_enabled) {
        if (!tree.getChain(g.ws_base, g.ws_tip, g.chain)) {
          RCLCPP_FATAL(get_logger(), "Group %s: no chain %s -> %s", g.name.c_str(), g.ws_base.c_str(), g.ws_tip.c_str());
          rclcpp::shutdown();
          return;
        }
        for (const auto & seg : g.chain.segments) {
          if (seg.getJoint().getType() == KDL::Joint::None) {
            continue;
          }
          const auto it = std::find(g.joints.begin(), g.joints.end(), seg.getJoint().getName());
          if (it == g.joints.end()) {
            RCLCPP_FATAL(get_logger(), "Group %s: chain joint %s not in group", g.name.c_str(),
              seg.getJoint().getName().c_str());
            rclcpp::shutdown();
            return;
          }
          g.chain_to_group.push_back(static_cast<std::size_t>(std::distance(g.joints.begin(), it)));
        }
        g.fk = std::make_unique<KDL::ChainFkSolverPos_recursive>(g.chain);
      }
    }
    last_cycle_ = SteadyClock::now();
    timer_ = create_wall_timer(
      std::chrono::duration<double>(1.0 / rate_hz_), [this]() {cycle();});
    RCLCPP_INFO(get_logger(), "Safety monitor running at %.0f Hz, %zu groups", rate_hz_, groups_.size());
  }

  std::optional<std::array<double, 3>> tip_position(Group & g, const std::vector<double> & q)
  {
    KDL::JntArray jq(static_cast<unsigned int>(g.chain_to_group.size()));
    for (std::size_t i = 0; i < g.chain_to_group.size(); ++i) {
      jq(static_cast<unsigned int>(i)) = q[g.chain_to_group[i]];
    }
    KDL::Frame f;
    if (g.fk->JntToCart(jq, f) < 0) {
      return std::nullopt;
    }
    return std::array<double, 3>{f.p.x(), f.p.y(), f.p.z()};
  }

  // Joint positions from /joint_states, or nullopt if any joint is missing or stale.
  std::optional<std::vector<double>> measured(const Group & g, SteadyClock::time_point now) const
  {
    std::vector<double> q;
    for (const auto & jn : g.joints) {
      const auto it = measured_.find(jn);
      if (it == measured_.end() ||
        std::chrono::duration<double>(now - it->second.stamp).count() > state_timeout_)
      {
        return std::nullopt;
      }
      q.push_back(it->second.position);
    }
    return q;
  }

  static const std::vector<double> & target_of(const std::optional<TeleopAction> & a, const std::string & group)
  {
    static const std::vector<double> empty;
    if (!a) {return empty;}
    if (group == "left_arm") {return a->left_arm;}
    if (group == "right_arm") {return a->right_arm;}
    if (group == "left_hand") {return a->left_hand;}
    if (group == "right_hand") {return a->right_hand;}
    return empty;
  }

  void cycle()
  {
    const auto now = SteadyClock::now();
    // Cap dt so a stalled cycle cannot produce a large step.
    const double dt = std::min(std::chrono::duration<double>(now - last_cycle_).count(), 2.0 / rate_hz_);
    last_cycle_ = now;

    const double age = action_ ? std::chrono::duration<double>(now - action_time_).count() : -1.0;
    const bool fresh = action_ && age <= command_timeout_;
    const bool deadman = fresh && action_->deadman;

    uint8_t state = SafetyState::STATE_ACTIVE;
    std::string reason;
    if (estop_latched_) {
      state = SafetyState::STATE_ESTOP;
      reason = estop_input_ ? "emergency stop" : "emergency stop latched (call ~/reset)";
    } else if (!action_) {
      state = SafetyState::STATE_HOLD;
      reason = "no command received";
    } else if (!fresh) {
      state = SafetyState::STATE_HOLD;
      reason = "command timeout";
    } else if (!deadman) {
      state = SafetyState::STATE_HOLD;
      reason = "deadman released";
    }

    SafetyState msg;
    for (auto & g : groups_) {
      const auto q = measured(g, now);
      if (!g.initialized) {
        if (!q) {
          continue;
        }
        g.out = *q;
        g.initialized = true;
      }
      if (!q) {
        msg.faulted_groups.push_back(g.name);
      }

      const bool group_active = state == SafetyState::STATE_ACTIVE && q.has_value();
      const auto & target = target_of(action_, g.name);
      if (!group_active || target.size() != g.joints.size()) {
        g.engaged = false;
        // The robot was moved by something else (e.g. trajectory controller): hold where it is now.
        if (q && max_abs_diff(*q, g.out) > resync_threshold_) {
          g.out = *q;
        }
      } else {
        if (!g.engaged && max_abs_diff(target, g.out) > g.max_start_error) {
          msg.limited_groups.push_back(g.name);
          if (reason.empty()) {
            reason = g.name + ": target too far from current position";
          }
        } else {
          g.engaged = true;
          auto cand = g.out;
          bool limited = limit_step(cand, target, g.lower, g.upper, g.vmax, dt);
          if (g.fk) {
            const auto p_new = tip_position(g, cand);
            const auto p_old = tip_position(g, g.out);
            // Allow motion that stays inside the box or moves back toward it.
            if (!p_new || !p_old ||
              distance_to_box(*p_new, g.ws_min, g.ws_max) > distance_to_box(*p_old, g.ws_min, g.ws_max) + 1e-9)
            {
              cand = g.out;
              limited = true;
            }
          }
          g.out = cand;
          if (limited) {
            msg.limited_groups.push_back(g.name);
          }
        }
      }

      Float64MultiArray cmd;
      cmd.data = g.out;
      g.pub->publish(cmd);
    }

    if (state == SafetyState::STATE_ACTIVE && !msg.faulted_groups.empty() && reason.empty()) {
      reason = "stale joint_states";
    }
    if (++cycle_count_ % static_cast<int>(rate_hz_ / 50.0) == 0 || state != last_state_) {
      msg.header.stamp = get_clock()->now();
      msg.state = state;
      msg.reason = reason;
      msg.estop = estop_latched_;
      msg.deadman = deadman;
      msg.command_age = age;
      state_pub_->publish(msg);
    }
    if (state != last_state_) {
      RCLCPP_INFO(get_logger(), "State %u -> %u (%s)", last_state_, state, reason.c_str());
      last_state_ = state;
    }
  }

  struct Measured
  {
    double position;
    SteadyClock::time_point stamp;
  };

  double rate_hz_, command_timeout_, state_timeout_, margin_, max_start_error_, resync_threshold_;
  std::vector<Group> groups_;
  std::map<std::string, Measured> measured_;
  std::optional<TeleopAction> action_;
  SteadyClock::time_point action_time_{};
  SteadyClock::time_point last_cycle_{};
  bool estop_input_{false};
  bool estop_latched_{false};
  uint8_t last_state_{255};
  long cycle_count_{0};

  rclcpp::Publisher<SafetyState>::SharedPtr state_pub_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr description_sub_;
  rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr joint_sub_;
  rclcpp::Subscription<TeleopAction>::SharedPtr action_sub_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr estop_sub_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr reset_srv_;
  rclcpp::TimerBase::SharedPtr timer_;
};

}  // namespace teleop_safety

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<teleop_safety::SafetyMonitor>());
  rclcpp::shutdown();
  return 0;
}
