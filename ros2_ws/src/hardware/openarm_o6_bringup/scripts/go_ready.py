#!/usr/bin/env python3
"""Move both arms to a ready pose with the trajectory controllers, then hand control back.

Works in either bringup mode; in mode:=teleop the forward controllers are restored afterwards and the
safety monitor re-syncs to the new position (resync_threshold).
"""

import argparse
import sys

import rclpy
from builtin_interfaces.msg import Duration
from control_msgs.action import FollowJointTrajectory
from controller_manager_msgs.srv import ListControllers, SwitchController
from rclpy.action import ActionClient
from rclpy.node import Node
from trajectory_msgs.msg import JointTrajectoryPoint

ARM_READY = [0.0, 0.0, 0.0, 1.2, 0.0, 0.0, 0.0]  # elbow bent, away from the straight-arm singularity
GROUPS = {
    'left_arm': [f'openarm_left_joint{i}' for i in range(1, 8)],
    'right_arm': [f'openarm_right_joint{i}' for i in range(1, 8)],
}


def call(node, client, req):
    client.wait_for_service(timeout_sec=5.0)
    fut = client.call_async(req)
    rclpy.spin_until_future_complete(node, fut, timeout_sec=10.0)
    return fut.result()


def switch(node, cli, activate, deactivate):
    req = SwitchController.Request(activate_controllers=activate, deactivate_controllers=deactivate,
                                   strictness=SwitchController.Request.STRICT)
    res = call(node, cli, req)
    if not res or not res.ok:
        raise RuntimeError(f'switch failed: activate={activate} deactivate={deactivate}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=float, default=4.0)
    args = parser.parse_args()

    rclpy.init()
    node = Node('go_ready')
    sw = node.create_client(SwitchController, '/controller_manager/switch_controller')
    ls = node.create_client(ListControllers, '/controller_manager/list_controllers')
    active = {c.name for c in call(node, ls, ListControllers.Request()).controller if c.state == 'active'}
    forward = [f'{g}_controller' for g in GROUPS if f'{g}_controller' in active]
    trajectory = [f'{g}_trajectory_controller' for g in GROUPS]

    if forward:
        switch(node, sw, trajectory, forward)
    try:
        futures = []
        for group, joints in GROUPS.items():
            ac = ActionClient(node, FollowJointTrajectory, f'/{group}_trajectory_controller/follow_joint_trajectory')
            ac.wait_for_server(timeout_sec=5.0)
            goal = FollowJointTrajectory.Goal()
            goal.trajectory.joint_names = joints
            sec = int(args.duration)
            goal.trajectory.points = [JointTrajectoryPoint(
                positions=ARM_READY, time_from_start=Duration(sec=sec, nanosec=int((args.duration - sec) * 1e9)))]
            futures.append(ac.send_goal_async(goal))
        for f in futures:
            rclpy.spin_until_future_complete(node, f)
            res_f = f.result().get_result_async()
            rclpy.spin_until_future_complete(node, res_f)
            if res_f.result().result.error_code != 0:
                print(f'trajectory failed: {res_f.result().result.error_string}')
                return 1
    finally:
        if forward:
            switch(node, sw, forward, trajectory)
    print('ready pose reached' + (', forward controllers restored' if forward else ''))
    rclpy.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
