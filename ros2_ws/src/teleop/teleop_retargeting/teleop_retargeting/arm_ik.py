"""Damped least-squares IK for one 7-DoF arm on a reduced Pinocchio model."""

import numpy as np
import pinocchio as pin


class ArmIK:
    def __init__(self, urdf_xml, joint_names, tip_frame, *, iterations=20, damping=1e-4,
                 rot_weight=0.3, posture_gain=0.02, max_step=0.2, tolerance=1e-4, limit_margin=0.03):
        full = pin.buildModelFromXML(urdf_xml)
        keep = set(joint_names)
        lock = [full.getJointId(n) for n in full.names[1:] if n not in keep]
        self.model = pin.buildReducedModel(full, lock, pin.neutral(full))
        self.data = self.model.createData()
        if not self.model.existFrame(tip_frame):
            raise ValueError(f'frame {tip_frame} not in URDF')
        self.frame = self.model.getFrameId(tip_frame)
        # Map our joint order <-> Pinocchio q index.
        self.q_index = np.array([self.model.joints[self.model.getJointId(n)].idx_q for n in joint_names])
        # Stay inside the safety monitor's soft limits (soft_limit_margin 0.02) so commands are not clamped.
        self.lower = self.model.lowerPositionLimit[self.q_index] + limit_margin
        self.upper = self.model.upperPositionLimit[self.q_index] - limit_margin
        self.posture = 0.5 * (self.lower + self.upper)
        self.iterations = iterations
        self.damping = damping
        self.weights = np.array([1.0, 1.0, 1.0, rot_weight, rot_weight, rot_weight])
        self.posture_gain = posture_gain
        self.max_step = max_step
        self.tolerance = tolerance

    def _to_model(self, q):
        qm = pin.neutral(self.model)
        qm[self.q_index] = q
        return qm

    def fk(self, q):
        """Tip pose (pin.SE3) in the URDF root frame for joints q (our order)."""
        qm = self._to_model(np.asarray(q, dtype=float))
        pin.forwardKinematics(self.model, self.data, qm)
        return pin.updateFramePlacement(self.model, self.data, self.frame).copy()

    def solve(self, q_seed, target):
        """Return (q, error_norm); q stays within URDF limits and moves at most max_step per iteration."""
        q = np.clip(np.asarray(q_seed, dtype=float), self.lower, self.upper)
        err_norm = np.inf
        for _ in range(self.iterations):
            qm = self._to_model(q)
            pin.forwardKinematics(self.model, self.data, qm)
            current = pin.updateFramePlacement(self.model, self.data, self.frame)
            err = pin.log6(current.actInv(target)).vector * self.weights
            err_norm = float(np.linalg.norm(err))
            if err_norm < self.tolerance:
                break
            jac = pin.computeFrameJacobian(self.model, self.data, qm, self.frame, pin.LOCAL)
            jac = (self.weights[:, None] * jac)[:, self.q_index]
            jjt = jac @ jac.T + self.damping * np.eye(6)
            dq = jac.T @ np.linalg.solve(jjt, err)
            # Null-space pull toward mid-range keeps the elbow away from limits.
            null = np.eye(len(q)) - np.linalg.pinv(jac) @ jac
            dq += null @ (self.posture_gain * (self.posture - q))
            dq = np.clip(dq, -self.max_step, self.max_step)
            q = np.clip(q + dq, self.lower, self.upper)
        return q, err_norm
