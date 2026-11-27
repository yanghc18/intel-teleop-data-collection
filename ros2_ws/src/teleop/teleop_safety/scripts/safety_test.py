#!/usr/bin/env python3
"""P3 safety acceptance test. Needs a running `bringup.launch.py mode:=teleop` (mock or real hardware)."""

import argparse
import statistics
import sys
import threading
import time

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool, Float64MultiArray
from std_srvs.srv import Trigger
from teleop_msgs.msg import SafetyState, TeleopAction

LEFT_ARM = [f'openarm_left_joint{i}' for i in range(1, 8)]
J1, J7 = 0, 6


class Tester(Node):
    def __init__(self):
        super().__init__('safety_test')
        self.lock = threading.Lock()
        self.cmd_log = []  # (monotonic time, command tuple)
        self.joints = {}
        self.state = None
        self.target_fn = None
        self.deadman = True
        self.last_action_t = None
        self.action_pub = self.create_publisher(TeleopAction, '/teleop_action', 1)
        self.estop_pub = self.create_publisher(
            Bool, '/emergency_stop', QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.create_subscription(Float64MultiArray, '/left_arm_controller/commands', self.on_cmd, 50)
        self.create_subscription(JointState, '/joint_states', self.on_js, qos_profile_sensor_data)
        self.create_subscription(SafetyState, '/teleop/safety_state', self.on_state, 10)
        self.reset_cli = self.create_client(Trigger, '/safety_monitor/reset')
        self.create_timer(0.01, self.stream)  # 100 Hz, like retargeting

    def on_cmd(self, msg):
        with self.lock:
            self.cmd_log.append((time.monotonic(), tuple(msg.data)))

    def on_js(self, msg):
        with self.lock:
            self.joints.update(zip(msg.name, msg.position))

    def on_state(self, msg):
        self.state = msg

    def stream(self):
        with self.lock:
            fn, deadman = self.target_fn, self.deadman
        if fn is None:
            return
        msg = TeleopAction()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.deadman = deadman
        msg.left_arm = [float(v) for v in fn(time.monotonic())]
        self.action_pub.publish(msg)
        with self.lock:
            self.last_action_t = time.monotonic()

    # --- helpers -------------------------------------------------------------
    def set_target(self, fn, deadman=True):
        with self.lock:
            self.target_fn, self.deadman = fn, deadman

    def stop_stream(self):
        with self.lock:
            self.target_fn = None
            t = self.last_action_t
        return t

    def out(self):
        with self.lock:
            return list(self.cmd_log[-1][1]) if self.cmd_log else None

    def freeze_latency(self, t_event, window):
        """Time from t_event to the last change of the command within [t_event, t_event+window]."""
        time.sleep(window)
        with self.lock:
            log = [e for e in self.cmd_log if e[0] >= t_event - 0.05]
        last_change = t_event
        for (_, prev), (t, cur) in zip(log, log[1:]):
            if cur != prev and t > last_change:
                last_change = t
        return last_change - t_event

    def reset_estop(self):
        self.estop_pub.publish(Bool(data=False))
        time.sleep(0.02)
        fut = self.reset_cli.call_async(Trigger.Request())
        while not fut.done():
            time.sleep(0.005)
        return fut.result().success


def offset(center, delta, joint=J1):
    q = list(center)
    q[joint] += delta
    return lambda t: q


CHASE = 0.18  # [rad] < max_start_error; at 1 rad/s the output moves for 180 ms, so events land mid-motion


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--estop-trials', type=int, default=100)
    parser.add_argument('--timeout-trials', type=int, default=20)
    args = parser.parse_args()

    rclpy.init()
    node = Tester()
    ex = MultiThreadedExecutor()
    ex.add_node(node)
    threading.Thread(target=ex.spin, daemon=True).start()
    results = []

    def record(name, passed, detail):
        results.append((name, passed, detail))
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}", flush=True)

    deadline = time.monotonic() + 10
    while (node.out() is None or node.state is None or not all(j in node.joints for j in LEFT_ARM)):
        if time.monotonic() > deadline:
            print('No /left_arm_controller/commands or safety state; is bringup running with mode:=teleop?')
            return 2
        time.sleep(0.1)
    node.reset_estop()
    center = node.out()
    node.set_target(lambda t: center)
    time.sleep(0.5)

    # T1 command timeout (communication loss): stop streaming while the output is still moving
    lat, short = [], 0
    for _ in range(args.timeout_trials):
        node.set_target(offset(center, CHASE))
        time.sleep(0.02)
        t_stop = node.stop_stream()
        lat.append(node.freeze_latency(t_stop, 0.3))
        reason = node.state.reason if node.state else ''
        short += node.out()[J1] < center[J1] + CHASE - 1e-3  # stopped before reaching the target
        node.set_target(lambda t: center)
        time.sleep(0.4)
    record('Command timeout -> hold', max(lat) <= 0.100 and short == len(lat) and 'timeout' in reason,
           f'n={len(lat)}, stop after last command: max {max(lat) * 1e3:.1f} ms, mean {statistics.mean(lat) * 1e3:.1f} ms '
           f'(limit 100 ms), stopped short of target {short}/{len(lat)}, reason="{reason}"')

    # T2 e-stop while moving; commands keep streaming during the e-stop
    lat, leaks = [], 0
    for _ in range(args.estop_trials):
        node.set_target(offset(center, CHASE))
        time.sleep(0.05)
        t_e = time.monotonic()
        node.estop_pub.publish(Bool(data=True))
        lat.append(node.freeze_latency(t_e, 0.15))
        frozen = node.out()
        time.sleep(0.05)
        leaks += node.out() != frozen
        if node.state.state != SafetyState.STATE_ESTOP:
            leaks += 1
        node.reset_estop()
        node.set_target(lambda t: center)
        time.sleep(0.3)
    record('E-stop', leaks == 0 and max(lat) <= 0.02,
           f'n={len(lat)}, effective {len(lat) - leaks}/{len(lat)}, latency max {max(lat) * 1e3:.1f} ms, '
           f'mean {statistics.mean(lat) * 1e3:.1f} ms')

    # T3 e-stop latch: reset refused while /emergency_stop is true
    node.estop_pub.publish(Bool(data=True))
    time.sleep(0.05)
    fut = node.reset_cli.call_async(Trigger.Request())
    while not fut.done():
        time.sleep(0.005)
    refused = not fut.result().success
    ok = node.reset_estop()
    record('E-stop latch', refused and ok, f'reset while pressed refused={refused}, reset after release ok={ok}')

    # T4 deadman release while moving
    lat = []
    for _ in range(10):
        node.set_target(offset(center, CHASE))
        time.sleep(0.05)
        t_e = time.monotonic()
        node.set_target(offset(center, CHASE), deadman=False)
        lat.append(node.freeze_latency(t_e, 0.1))
        node.set_target(lambda t: center)
        time.sleep(0.3)
    record('Deadman release -> hold', max(lat) <= 0.03, f'n=10, max {max(lat) * 1e3:.1f} ms (one 100 Hz action + one 500 Hz cycle)')

    # T5 soft position limit (joint7 URDF upper 1.5708, margin 0.02)
    tgt = list(center)
    tgt[J7] = 2.5
    node.set_target(lambda t: tgt)
    time.sleep(2.5)
    q7 = node.out()[J7]
    limited = 'left_arm' in node.state.limited_groups
    record('Soft position limit', abs(q7 - (1.5708 - 0.02)) < 1e-3 and limited, f'target 2.5 -> output {q7:.4f} rad')

    # T6 velocity limit (1.0 rad/s)
    tgt = list(center)
    tgt[J7] = -1.0
    t0, q0 = time.monotonic(), node.out()[J7]
    node.set_target(lambda t: tgt)
    time.sleep(0.5)
    t1, q1 = time.monotonic(), node.out()[J7]
    v = abs(q1 - q0) / (t1 - t0)
    record('Velocity limit', v <= 1.05, f'step 2.5 rad -> {v:.3f} rad/s (limit 1.0)')
    node.set_target(lambda t: center)
    time.sleep(2.0)

    # T7 refuse to engage on a far target after hold
    node.stop_stream()
    time.sleep(0.2)
    before = node.out()
    far = list(before)
    far[J1] += 0.5
    node.set_target(lambda t: far)
    time.sleep(0.3)
    moved = node.out() != before
    reason = node.state.reason
    node.set_target(lambda t: before)
    time.sleep(0.3)
    record('Refuse far start target', not moved and 'too far' in reason, f'0.5 rad jump: moved={moved}, reason="{reason}"')

    node.stop_stream()
    ok = all(p for _, p, _ in results)
    print('\n| Test | Result | Detail |\n|---|---|---|')
    for name, p, d in results:
        print(f"| {name} | {'PASS' if p else 'FAIL'} | {d} |")
    ex.shutdown()
    rclpy.shutdown()
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
