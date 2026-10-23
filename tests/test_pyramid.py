"""Validate the executable packing against the rigid pieces and support order."""
import unittest

import numpy as np
from scipy.optimize import linear_sum_assignment

from puzzler import model
from puzzler.pyramid import SITES, get_plan, physical


class TestRobotPacking(unittest.TestCase):
    def test_cover_preserves_all_rigid_shapes(self):
        placements = get_plan('pyramid_robot6_plan.json')['placements']
        self.assertEqual(set(placements), set(model.CELLS))
        sites = [tuple(s) for v in placements.values() for s in v['sites']]
        self.assertEqual(len(sites), 55)
        self.assertEqual(set(sites), set(SITES))
        for name, part in placements.items():
            rotation = np.array(part['R'])
            np.testing.assert_allclose(rotation.T @ rotation, np.eye(3), atol=1e-12)
            self.assertAlmostEqual(np.linalg.det(rotation), 1.)
            actual = model.local_beads(name) @ rotation.T + part['center']
            cost = np.linalg.norm(actual[:, None] - physical(part['sites'])[None, :], axis=2)
            a, b = linear_sum_assignment(cost)
            self.assertLess(cost[a, b].max(), 1e-10, name)

    def test_supports_admit_an_assembly_order(self):
        placements = get_plan('pyramid_robot6_plan.json')['placements']
        support = {}
        for name, part in placements.items():
            below = {(x + dx, y + dy, z - 1) for x, y, z in part['sites']
                     for dx in [-1, 1] for dy in [-1, 1]}
            support[name] = {other for other, v in placements.items()
                             if other != name and below.intersection(map(tuple, v['sites']))}
        done = set()
        while len(done) < 12:
            ready = {name for name in placements if name not in done and support[name] <= done}
            self.assertTrue(ready, 'A support cycle would require moving through a seated piece.')
            done.update(ready)


if __name__ == '__main__':
    unittest.main()
