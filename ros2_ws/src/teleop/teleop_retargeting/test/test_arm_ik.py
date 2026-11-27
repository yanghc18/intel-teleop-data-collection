"""IK on the real OpenARM + O6 URDF (needs the built workspace for xacro)."""

import shutil
import subprocess

import numpy as np
import pinocchio as pin
import pytest

from teleop_retargeting.arm_ik import ArmIK

JOINTS = [f'openarm_right_joint{i}' for i in range(1, 8)]


@pytest.fixture(scope='module')
def ik():
    if shutil.which('ros2') is None:
        pytest.skip('ROS environment not sourced')
    try:
        prefix = subprocess.check_output(['ros2', 'pkg', 'prefix', 'openarm_o6_description'], text=True).strip()
    except subprocess.CalledProcessError:
        pytest.skip('openarm_o6_description not built')
    urdf = subprocess.check_output(
        ['xacro', f'{prefix}/share/openarm_o6_description/urdf/openarm_o6.urdf.xacro'], text=True)
    return ArmIK(urdf, JOINTS, 'rh_hand_base_link')


def test_reaches_random_reachable_targets(ik):
    rng = np.random.default_rng(0)
    worst = 0.0
    for _ in range(50):
        q_goal = rng.uniform(ik.lower + 0.2, ik.upper - 0.2)
        seed = np.clip(q_goal + rng.normal(0, 0.1, 7), ik.lower, ik.upper)
        target = ik.fk(q_goal)
        q, _ = ik.solve(seed, target)
        reached = ik.fk(q)
        worst = max(worst, np.linalg.norm(reached.translation - target.translation))
    assert worst < 1e-3


def test_respects_joint_limits(ik):
    reach = ik.fk(ik.upper)
    far = pin.SE3(reach.rotation, reach.translation + np.array([0.0, 0.0, 5.0]))  # unreachable
    q, err = ik.solve(ik.posture, far)
    assert np.all(q >= ik.lower - 1e-12) and np.all(q <= ik.upper + 1e-12)
    assert err > 0.1
