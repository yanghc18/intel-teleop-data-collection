"""XR frame conventions -> ROS (x forward, y left, z up, right-handed)."""

import numpy as np

# OpenXR: right-handed, x right, y up, -z forward.
_OPENXR = np.array([[0.0, 0.0, -1.0], [-1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
# Unity: left-handed, x right, y up, z forward (det = -1).
_UNITY = np.array([[0.0, 0.0, 1.0], [-1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])

CONVENTIONS = {'openxr': _OPENXR, 'unity': _UNITY}


def to_ros(pose7, convention):
    """[x, y, z, qx, qy, qz, qw] in the XR frame -> (position, quaternion xyzw) in the ROS frame."""
    m = CONVENTIONS[convention]
    p = m @ np.asarray(pose7[:3], dtype=float)
    v = m @ np.asarray(pose7[3:6], dtype=float)
    # Quaternion vector part is a pseudovector: it flips sign under a reflection (det = -1).
    v *= np.linalg.det(m)
    q = np.array([v[0], v[1], v[2], float(pose7[6])])
    return p, q / np.linalg.norm(q)
