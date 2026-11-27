import numpy as np
import pinocchio as pin
import pytest

from teleop_retargeting.hand_map import HandMap
from teleop_retargeting.mapping import relative_target, rot_z

SPEC = {
    'a': {'inputs': ['X', 'Y'], 'in_range': [0.0, 1.0], 'out_range': [0.0, 2.0]},
    'b': {'inputs': ['Z'], 'in_range': [1.0, 0.0], 'out_range': [0.5, 1.5]},
}


def test_hand_map_linear_and_clamped():
    m = HandMap(SPEC, ['a', 'b'])
    assert m.map(['X', 'Y', 'Z'], [0.5, 0.5, 1.0]) == [1.0, 0.5]
    assert m.map(['X', 'Y', 'Z'], [3.0, 3.0, -1.0]) == [2.0, 1.5]
    assert m.map(['X', 'Z'], [0.5, 0.5]) is None


def test_hand_map_calibration():
    m = HandMap(SPEC, ['a', 'b'])
    assert m.calibrate(['X', 'Y', 'Z'], [0.2, 0.2, 0.9], 0)
    assert m.calibrate(['X', 'Y', 'Z'], [0.6, 0.6, 0.1], 1)
    assert m.map(['X', 'Y', 'Z'], [0.4, 0.4, 0.5]) == pytest.approx([1.0, 1.0])


def test_relative_target_translation_and_rotation():
    anchor_op = pin.SE3(np.eye(3), np.array([1.0, 1.0, 1.0]))
    now_op = pin.SE3(rot_z(0.3), np.array([1.1, 1.0, 1.0]))
    anchor_robot = pin.SE3(np.eye(3), np.array([0.5, 0.0, 0.2]))
    # Operator faces +y in their frame: align rotates by -90 deg about z.
    t = relative_target(anchor_op, now_op, anchor_robot, rot_z(-np.pi / 2), 2.0)
    np.testing.assert_allclose(t.translation, [0.5, -0.2, 0.2], atol=1e-12)
    np.testing.assert_allclose(t.rotation, rot_z(0.3), atol=1e-12)
