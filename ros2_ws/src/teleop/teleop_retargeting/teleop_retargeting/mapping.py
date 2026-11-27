"""Clutch-relative mapping of operator motion onto the robot end effector."""

import numpy as np
import pinocchio as pin


def se3_from_pose(p):
    """geometry_msgs/Pose -> pin.SE3."""
    q = pin.Quaternion(p.orientation.w, p.orientation.x, p.orientation.y, p.orientation.z)
    q.normalize()
    return pin.SE3(q.matrix(), np.array([p.position.x, p.position.y, p.position.z]))


def rot_z(yaw):
    c, s = np.cos(yaw), np.sin(yaw)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def yaw_of(rotation):
    return float(np.arctan2(rotation[1, 0], rotation[0, 0]))


def relative_target(op_anchor, op_now, robot_anchor, align, scale):
    """Apply the operator's motion since the clutch was engaged to the robot anchor pose.

    align rotates operator-frame vectors into the robot base frame; scale applies to translation only.
    """
    dp = align @ (op_now.translation - op_anchor.translation) * scale
    dr = align @ (op_now.rotation @ op_anchor.rotation.T) @ align.T
    return pin.SE3(dr @ robot_anchor.rotation, robot_anchor.translation + dp)
