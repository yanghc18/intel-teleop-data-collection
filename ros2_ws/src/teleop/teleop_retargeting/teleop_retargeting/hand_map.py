"""Glove joint angles -> O6 joint positions (linear map per O6 joint, calibratable)."""

import numpy as np


class HandMap:
    """spec[o6_joint] = {'inputs': [...], 'in_range': [open, closed], 'out_range': [lo, hi]}."""

    def __init__(self, spec, o6_joints):
        self.o6_joints = list(o6_joints)
        self.spec = {j: {'inputs': list(spec[j]['inputs']),
                         'in_range': [float(v) for v in spec[j]['in_range']],
                         'out_range': [float(v) for v in spec[j]['out_range']]}
                     for j in self.o6_joints}

    def input_values(self, names, angles):
        """Average of the configured glove inputs per O6 joint, or None if any input is missing."""
        lookup = dict(zip(names, angles))
        values = {}
        for j, s in self.spec.items():
            try:
                values[j] = float(np.mean([lookup[n] for n in s['inputs']]))
            except KeyError:
                return None
        return values

    def map(self, names, angles):
        values = self.input_values(names, angles)
        if values is None:
            return None
        out = []
        for j in self.o6_joints:
            (a, b), (lo, hi) = self.spec[j]['in_range'], self.spec[j]['out_range']
            t = 0.0 if b == a else (values[j] - a) / (b - a)
            out.append(lo + float(np.clip(t, 0.0, 1.0)) * (hi - lo))
        return out

    def calibrate(self, names, angles, end):
        """Store the current glove pose as the 'open' (end=0) or 'closed' (end=1) end of every input range."""
        values = self.input_values(names, angles)
        if values is None:
            return False
        for j, v in values.items():
            self.spec[j]['in_range'][end] = v
        return True
