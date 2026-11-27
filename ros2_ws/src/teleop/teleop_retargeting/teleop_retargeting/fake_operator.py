"""Simulated operator: Pico head + wrist tracker poses, Manus finger angles and the deadman pedal."""

import math

import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import Bool
from teleop_msgs.msg import HandSkeleton

FINGERS = ['Thumb', 'Index', 'Middle', 'Ring', 'Pinky']
GLOVE_JOINTS = [f'{f}{j}' for f in FINGERS for j in ('MCPSpread', 'MCPStretch', 'PIPStretch', 'DIPStretch')]


def pose_msg(stamp, xyz, roll):
    m = PoseStamped()
    m.header.stamp, m.header.frame_id = stamp, 'pico_world'
    m.pose.position.x, m.pose.position.y, m.pose.position.z = xyz
    m.pose.orientation.x, m.pose.orientation.w = math.sin(roll / 2), math.cos(roll / 2)
    return m


class FakeOperator(Node):
    def __init__(self):
        super().__init__('fake_operator')
        self.radius = self.declare_parameter('radius', 0.05).value
        self.period = self.declare_parameter('period', 4.0).value
        self.deadman_toggle = self.declare_parameter('deadman_toggle_period', 0.0).value
        self.pose_pub = {k: self.create_publisher(PoseStamped, f'/pico/{k}_pose', qos_profile_sensor_data)
                         for k in ('head', 'left_hand', 'right_hand')}
        self.glove_pub = {s: self.create_publisher(HandSkeleton, f'/manus/{s}_hand', qos_profile_sensor_data)
                          for s in ('left', 'right')}
        self.deadman_pub = self.create_publisher(Bool, '/teleop/deadman', 10)
        self.t0 = self.get_clock().now()
        self.create_timer(1.0 / 90.0, self.publish_xr)     # Pico display rate
        self.create_timer(1.0 / 50.0, self.publish_pedal)

    def phase(self):
        t = (self.get_clock().now() - self.t0).nanoseconds * 1e-9
        return t, 2 * math.pi * t / self.period

    def publish_xr(self):
        t, w = self.phase()
        stamp = self.get_clock().now().to_msg()
        self.pose_pub['head'].publish(pose_msg(stamp, (0.0, 0.0, 1.6), 0.0))
        for side, y in (('left', 0.2), ('right', -0.2)):
            xyz = (0.3, y + self.radius * math.cos(w), 1.1 + self.radius * math.sin(w))
            self.pose_pub[f'{side}_hand'].publish(pose_msg(stamp, xyz, 0.3 * math.sin(w)))
            flex = 0.75 * (1 - math.cos(w))  # 0 (open) .. 1.5 rad (fist)
            angles = [0.3 * flex / 1.5 if j.endswith('Spread') else flex for j in GLOVE_JOINTS]
            self.glove_pub[side].publish(HandSkeleton(side=side, joint_names=GLOVE_JOINTS, joint_angles=angles,
                                                      header=pose_msg(stamp, (0, 0, 0), 0).header))

    def publish_pedal(self):
        t, _ = self.phase()
        pressed = True if self.deadman_toggle <= 0 else int(t / self.deadman_toggle) % 2 == 0
        self.deadman_pub.publish(Bool(data=pressed))


def main():
    rclpy.init()
    rclpy.spin(FakeOperator())


if __name__ == '__main__':
    main()
