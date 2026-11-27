"""Latency probe: step the simulated left wrist pose and time each stage of the teleop chain.

Run instead of fake_operator, with retarget_node and the bringup (mode:=teleop) running.
"""

import statistics
import threading
import time

import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool, Float64MultiArray
from teleop_msgs.msg import TeleopAction

LEFT_ARM = [f'openarm_left_joint{i}' for i in range(1, 8)]


class Probe(Node):
    def __init__(self):
        super().__init__('latency_probe')
        self.lock = threading.Lock()
        self.x = 0.3
        self.t_step = None
        self.first = {}
        self.last = {}
        self.pose_pub = self.create_publisher(PoseStamped, '/pico/left_hand_pose', qos_profile_sensor_data)
        self.deadman_pub = self.create_publisher(Bool, '/teleop/deadman', 10)
        self.create_subscription(TeleopAction, '/teleop_action',
                                 lambda m: self.seen('action', tuple(m.left_arm)), 10)
        self.create_subscription(Float64MultiArray, '/left_arm_controller/commands',
                                 lambda m: self.seen('safety', tuple(m.data)), 10)
        self.create_subscription(JointState, '/joint_states', self.on_js, qos_profile_sensor_data)
        self.create_timer(1.0 / 90.0, self.publish)

    def on_js(self, m):
        pos = dict(zip(m.name, m.position))
        if LEFT_ARM[0] in pos:
            self.seen('joint_states', tuple(round(pos[j], 9) for j in LEFT_ARM))

    def seen(self, stage, value):
        now = time.monotonic()
        with self.lock:
            if self.t_step is not None and stage not in self.first and value and value != self.last.get(stage):
                self.first[stage] = now - self.t_step
            if self.t_step is None or stage in self.first:
                self.last[stage] = value

    def publish(self):
        m = PoseStamped()
        m.header.stamp, m.header.frame_id = self.get_clock().now().to_msg(), 'pico_world'
        m.pose.position.x, m.pose.position.y, m.pose.position.z = self.x, 0.2, 1.1
        m.pose.orientation.w = 1.0
        self.pose_pub.publish(m)
        self.deadman_pub.publish(Bool(data=True))

    def step(self, dx):
        with self.lock:
            self.first = {}
            self.x += dx
            self.t_step = time.monotonic()


def main():
    rclpy.init()
    node = Probe()
    ex = MultiThreadedExecutor()
    ex.add_node(node)
    threading.Thread(target=ex.spin, daemon=True).start()
    time.sleep(2.0)  # engage the clutch
    results = {k: [] for k in ('action', 'safety', 'joint_states')}
    for i in range(30):
        node.step(0.02 if i % 2 == 0 else -0.02)
        time.sleep(0.5)
        with node.lock:
            for k in results:
                if k in node.first:
                    results[k].append(node.first[k] * 1e3)
    print('| Stage (from wrist pose publish) | n | mean [ms] | max [ms] |\n|---|---|---|---|')
    for k, v in results.items():
        if v:
            print(f'| {k} | {len(v)} | {statistics.mean(v):.1f} | {max(v):.1f} |')
        else:
            print(f'| {k} | 0 | - | - |')
    ex.shutdown()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
