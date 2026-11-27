"""Pico 4 Ultra -> /pico/head_pose, /pico/{left,right}_hand_pose via the XRoboToolkit Python SDK.

Wrist poses come from two Pico Motion Trackers (one per wrist, matched by serial number) or,
for testing without trackers, from the controllers. Not yet verified with a headset.
"""

import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

from pico_bridge.xr_frames import CONVENTIONS, to_ros


class PicoBridge(Node):
    def __init__(self):
        super().__init__('pico_bridge')
        p = self.declare_parameter
        self.source = p('wrist_source', 'motion_tracker').value   # motion_tracker | controller
        self.convention = p('input_convention', 'openxr').value    # openxr | unity
        self.serial = {'left': p('left_tracker_serial', '').value, 'right': p('right_tracker_serial', '').value}
        rate = p('rate_hz', 90.0).value
        if self.convention not in CONVENTIONS:
            raise ValueError(f'input_convention must be one of {list(CONVENTIONS)}')

        import xrobotoolkit_sdk as xrt  # pip install xrobotoolkit-sdk; needs XRoboToolkit PC Service running
        self.xrt = xrt
        xrt.init()
        self.pub = {k: self.create_publisher(PoseStamped, f'/pico/{k}_pose', qos_profile_sensor_data)
                    for k in ('head', 'left_hand', 'right_hand')}
        self.create_timer(1.0 / rate, self.tick)
        self.get_logger().info(f'wrist source: {self.source}, input convention: {self.convention}')

    def wrist_poses(self):
        if self.source == 'controller':
            return {'left': self.xrt.get_left_controller_pose(), 'right': self.xrt.get_right_controller_pose()}
        if self.xrt.num_motion_data_available() < 2:
            return {}
        poses = dict(zip(self.xrt.get_motion_tracker_serial_numbers(), self.xrt.get_motion_tracker_pose()))
        return {side: poses[sn] for side, sn in self.serial.items() if sn in poses}

    def publish(self, key, pose7, stamp):
        pos, quat = to_ros(pose7, self.convention)
        m = PoseStamped()
        m.header.stamp, m.header.frame_id = stamp, 'pico_world'
        m.pose.position.x, m.pose.position.y, m.pose.position.z = (float(v) for v in pos)
        (m.pose.orientation.x, m.pose.orientation.y,
         m.pose.orientation.z, m.pose.orientation.w) = (float(v) for v in quat)
        self.pub[key].publish(m)

    def tick(self):
        # Stamped on receipt; the PC Service clock is not synchronized with ROS time.
        stamp = self.get_clock().now().to_msg()
        self.publish('head', self.xrt.get_headset_pose(), stamp)
        for side, pose7 in self.wrist_poses().items():
            self.publish(f'{side}_hand', pose7, stamp)

    def destroy_node(self):
        self.xrt.close()
        super().destroy_node()


def main():
    rclpy.init()
    rclpy.spin(PicoBridge())


if __name__ == '__main__':
    main()
