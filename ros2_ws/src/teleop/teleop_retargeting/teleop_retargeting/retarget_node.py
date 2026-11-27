"""Operator inputs -> /teleop_action.

Arms: wrist tracker pose (clutch-relative) -> damped least-squares IK.
Hands: glove joint angles -> O6 joints (linear map, calibratable).
"""

import time

import numpy as np
import rclpy
import yaml
from geometry_msgs.msg import PoseStamped
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, qos_profile_sensor_data
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger
from teleop_msgs.msg import HandSkeleton, TeleopAction

from teleop_retargeting.arm_ik import ArmIK
from teleop_retargeting.hand_map import HandMap
from teleop_retargeting.mapping import relative_target, rot_z, se3_from_pose, yaw_of


class Side:
    def __init__(self):
        self.pose = None          # latest operator wrist pose (pin.SE3)
        self.pose_stamp = None
        self.pose_t = 0.0
        self.skeleton = None
        self.skeleton_t = 0.0
        self.engaged = False
        self.q = None
        self.op_anchor = None
        self.robot_anchor = None


class RetargetNode(Node):
    def __init__(self):
        super().__init__('retarget_node')
        p = self.declare_parameter
        self.rate = p('rate_hz', 100.0).value
        self.scale = p('translation_scale', 1.0).value
        self.input_timeout = p('input_timeout', 0.1).value
        self.deadman_timeout = p('deadman_timeout', 0.2).value
        self.robot_yaw = p('robot_forward_yaw', 0.0).value
        self.sides = list(p('sides', ['left', 'right']).value)
        hand_file = p('hand_map_file', '').value
        self.arm_joints = {s: list(p(f'{s}.arm_joints', ['']).value) for s in self.sides}
        self.tip = {s: p(f'{s}.tip_frame', '').value for s in self.sides}

        with open(hand_file) as f:
            hand_cfg = yaml.safe_load(f)
        self.hand_map = {s: HandMap(hand_cfg['map'], hand_cfg['o6_joints']) for s in self.sides}

        self.align = rot_z(self.robot_yaw)
        self.head = None
        self.deadman = False
        self.deadman_t = 0.0
        self.measured = {}
        self.ik = {}
        self.side = {s: Side() for s in self.sides}

        self.pub = self.create_publisher(TeleopAction, '/teleop_action', 1)
        self.create_subscription(String, '/robot_description', self.on_description,
                                 QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.create_subscription(JointState, '/joint_states', self.on_joints, qos_profile_sensor_data)
        self.create_subscription(Bool, '/teleop/deadman', self.on_deadman, 10)
        self.create_subscription(PoseStamped, '/pico/head_pose', self.on_head, qos_profile_sensor_data)
        for s in self.sides:
            self.create_subscription(PoseStamped, f'/pico/{s}_hand_pose',
                                     lambda m, s=s: self.on_pose(s, m), qos_profile_sensor_data)
            self.create_subscription(HandSkeleton, f'/manus/{s}_hand',
                                     lambda m, s=s: self.on_skeleton(s, m), qos_profile_sensor_data)
        self.create_service(Trigger, '~/calibrate', self.on_calibrate)
        self.create_service(Trigger, '~/calibrate_hands_open', lambda q, r: self.on_hand_calib(r, 0))
        self.create_service(Trigger, '~/calibrate_hands_closed', lambda q, r: self.on_hand_calib(r, 1))
        self.create_timer(1.0 / self.rate, self.tick)

    # --- inputs ------------------------------------------------------------
    def on_description(self, msg):
        if self.ik:
            return
        try:
            self.ik = {s: ArmIK(msg.data, self.arm_joints[s], self.tip[s]) for s in self.sides}
            self.get_logger().info(f'IK ready for {self.sides}')
        except Exception as e:  # noqa: BLE001 - report and keep waiting for a valid description
            self.get_logger().error(f'IK setup failed: {e}')

    def on_joints(self, msg):
        self.measured.update(zip(msg.name, msg.position))

    def on_deadman(self, msg):
        self.deadman, self.deadman_t = msg.data, time.monotonic()

    def on_head(self, msg):
        self.head = se3_from_pose(msg.pose)

    def on_pose(self, s, msg):
        st = self.side[s]
        st.pose, st.pose_stamp, st.pose_t = se3_from_pose(msg.pose), msg.header.stamp, time.monotonic()

    def on_skeleton(self, s, msg):
        st = self.side[s]
        st.skeleton, st.skeleton_t = msg, time.monotonic()

    # --- services ----------------------------------------------------------
    def on_calibrate(self, _req, res):
        """Align the operator's facing direction (head yaw) with the robot forward direction."""
        if self.head is None:
            res.success, res.message = False, 'no /pico/head_pose'
            return res
        self.align = rot_z(self.robot_yaw - yaw_of(self.head.rotation))
        for st in self.side.values():
            st.engaged = False
        res.success, res.message = True, f'operator yaw {np.degrees(yaw_of(self.head.rotation)):.1f} deg'
        return res

    def on_hand_calib(self, res, end):
        done = [s for s, st in self.side.items()
                if st.skeleton and self.hand_map[s].calibrate(st.skeleton.joint_names, st.skeleton.joint_angles, end)]
        res.success = len(done) == len(self.sides)
        res.message = f"{'closed' if end else 'open'} pose stored for {done}"
        return res

    # --- main loop ---------------------------------------------------------
    def tick(self):
        now = time.monotonic()
        deadman = self.deadman and now - self.deadman_t < self.deadman_timeout
        act = TeleopAction(deadman=deadman)
        stamps = []
        for s, st in self.side.items():
            if self.ik and deadman and st.pose is not None and now - st.pose_t < self.input_timeout:
                ik = self.ik[s]
                if not st.engaged:
                    q = [self.measured.get(j) for j in self.arm_joints[s]]
                    if None in q:
                        continue
                    # Clutch engaged: anchor operator and robot poses so motion is relative.
                    st.q = np.array(q)
                    st.op_anchor, st.robot_anchor = st.pose, ik.fk(st.q)
                    st.engaged = True
                    self.get_logger().info(f'{s} clutch engaged')
                target = relative_target(st.op_anchor, st.pose, st.robot_anchor, self.align, self.scale)
                st.q, _ = ik.solve(st.q, target)
                setattr(act, f'{s}_arm', st.q.tolist())
                stamps.append(st.pose_stamp)
            else:
                if st.engaged:
                    self.get_logger().info(f'{s} clutch released')
                st.engaged = False

            if deadman and st.skeleton is not None and now - st.skeleton_t < self.input_timeout:
                hand = self.hand_map[s].map(st.skeleton.joint_names, st.skeleton.joint_angles)
                if hand is not None:
                    setattr(act, f'{s}_hand', hand)

        # Stamp with the oldest contributing input so latency is measured end to end.
        if stamps:
            act.header.stamp = min(stamps, key=lambda t: (t.sec, t.nanosec))
        else:
            act.header.stamp = self.get_clock().now().to_msg()
        self.pub.publish(act)


def main():
    rclpy.init()
    rclpy.spin(RetargetNode())


if __name__ == '__main__':
    main()
