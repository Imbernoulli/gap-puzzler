"""Sensor adapter and observable goal assessment, separate from the evaluator."""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.transform import Rotation

from . import model
from .vision import calibration, estimate, rig_specs


def goals(mode='flat', pyramid_plan='pyramid_robot6_plan.json'):
    """Public task specification/CAD. These are desired poses, never observations."""
    if mode == 'pyramid':
        raw = json.loads((model.ROOT/'assets'/pyramid_plan).read_text())
        return {n: (np.array(v['center']), np.array(v['R'])) for n, v in raw['placements'].items()}
    return {n: (model.target_center(n), np.eye(3)) for n in model.CELLS}


def assess(observation, targets):
    """Image-derived goal residuals; missing/uncertain pieces cannot pass."""
    poses = observation['poses']
    errors = {n: None for n in targets}
    if 'board' in poses:
        b = np.array(poses['board'])
        Rb = Rotation.from_quat(b[3:]).as_matrix()
        for n, (center, R) in targets.items():
            if n not in poses:
                continue
            p = np.array(poses[n])
            actual = model.local_beads(n) @ Rotation.from_quat(p[3:]).as_matrix().T+p[:3]
            desired = (model.local_beads(n) @ R.T+center) @ Rb.T+b[:3]
            cost = np.linalg.norm(actual[:, None]-desired[None, :], axis=2)
            ii, jj = linear_sum_assignment(cost)
            errors[n] = float(cost[ii, jj].max())
    return dict(bead_error_m=errors, all_visible=all(n in poses for n in ['board', *targets]),
                goal_geometry_consistent=all(e is not None and e < .004 for e in errors.values()),
                source='RGB pose estimates and public goal CAD; not evaluator success')


class RGBSensor:
    """The only adapter holding a simulator: it outputs RGB, calibration and time."""
    def __init__(self, env):
        self.env = env
        self.specs = rig_specs()
        self.cameras = calibration(self.specs)
        self.renderer = env.make_renderer('tiled', cameras=self.specs, channels=['rgb'])

    def capture(self):
        frames = self.renderer.render(self.env.state)
        if any(set(frame) != {'rgb'} for frame in frames.values()):
            raise ValueError('RGB sensor returned an undeclared channel')
        return ({key: np.asarray(frame['rgb'])[..., :3].copy() for key, frame in frames.items()},
                float(self.env.step_count/self.env.pipeline.control_hz))


class VisualObserver:
    """Does not hold the environment or evaluator; accepts a sensor function."""
    def __init__(self, capture, cameras, targets, output=None):
        self.capture = capture
        self.cameras = cameras
        self.targets = targets
        self.previous = {}
        self.last = None
        self.records = []
        self.output = Path(output) if output else None
        if self.output:
            self.output.mkdir(parents=True, exist_ok=True)

    def observe(self, hints=None):
        images, timestamp = self.capture()
        seeds = {**self.previous, **(hints or {})}
        result = estimate(images, self.cameras, seeds)
        result['timestamp'] = timestamp
        result['assessment'] = assess(result, self.targets)
        result['frame_sha256'] = {k: hashlib.sha256(a.tobytes()).hexdigest() for k, a in images.items()}
        if self.output:
            # Persist the actual sensor input. No ground truth is written here.
            np.savez_compressed(self.output/f'{len(self.records):04d}.npz', **images)
        self.previous.update(result['poses'])
        self.last = result
        self.records.append(result)
        if self.output:
            (self.output/'observations.json').write_text(json.dumps(self.records, indent=2))
        return result
