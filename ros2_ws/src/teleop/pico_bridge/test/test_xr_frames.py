import numpy as np
import pytest

from pico_bridge.xr_frames import CONVENTIONS, to_ros


def quat_to_mat(x, y, z, w):
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


@pytest.mark.parametrize('convention', list(CONVENTIONS))
def test_rotation_matches_basis_change(convention):
    rng = np.random.default_rng(1)
    m = CONVENTIONS[convention]
    for _ in range(20):
        q = rng.normal(size=4)
        q /= np.linalg.norm(q)
        p = rng.normal(size=3)
        pos, quat = to_ros([*p, *q], convention)
        np.testing.assert_allclose(pos, m @ p)
        # Same physical rotation expressed in the ROS basis.
        np.testing.assert_allclose(quat_to_mat(*quat), m @ quat_to_mat(*q) @ m.T, atol=1e-12)


def test_openxr_axes():
    # OpenXR forward is -z, up is +y.
    pos, _ = to_ros([0, 1, -2, 0, 0, 0, 1], 'openxr')
    np.testing.assert_allclose(pos, [2, 0, 1])
