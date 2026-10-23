import unittest
import numpy as np
from types import SimpleNamespace
from puzzler import model as m
from puzzler.task import grade

class TestChallenge(unittest.TestCase):
    def test_exact_cover_from_challenge(self):
        occupied=[p for n,cs in m.CELLS.items() if n not in m.MISSING for p in cs]
        ans=m.solve(occupied)
        cells=occupied+[tuple(c) for v in ans.values() for c in v['cells']]
        self.assertEqual(len(cells),55);self.assertEqual(len(set(cells)),55)
        for n,v in ans.items():self.assertEqual(set(map(tuple,v['cells'])),set(m.CELLS[n]))
    def test_unsatisfiable_observation(self):
        self.assertIsNone(m.solve([(r,c) for r in range(5) for c in range(11)]))

class FakeEnv:
    def __init__(self):
        self.ps={'board':np.r_[m.ORIGIN+m.BOARD_AT,0,0,0,1.]}
        self.ps.update({n:np.r_[m.ORIGIN+m.BOARD_AT+m.target_center(n),0,0,0,1.] for n in m.CELLS})
        self.width=.075;self.tcp=np.array([.4,0.,1.05])
        self.state=None
    def __getitem__(self,n):return SimpleNamespace(pose=self.ps[n],velocity=np.zeros(6))
    def arm(self,n):return SimpleNamespace(ee_pose=lambda state:(self.tcp,np.array([0,0,0,1.])))
    def gripper(self,n):return SimpleNamespace(width=lambda state:self.width)
    def state_is_finite(self):return True

class TestStrictGrader(unittest.TestCase):
    def test_complete_released_board(self):self.assertTrue(grade(FakeEnv())['success'])
    def test_airborne_piece_rejected(self):
        e=FakeEnv();e.ps['navy'][2]+=.08;self.assertFalse(grade(e)['success'])
    def test_one_wrong_bead_footprint_rejected(self):
        e=FakeEnv();e.ps['red'][0]+=.008;self.assertFalse(grade(e)['success'])
    def test_closed_hands_rejected(self):
        e=FakeEnv();e.width=.01;self.assertFalse(grade(e)['success'])
    def test_airborne_board_rejected(self):
        e=FakeEnv()
        for p in e.ps.values():p[2]+=.05
        self.assertFalse(grade(e)['success'])
    def test_nearby_hands_rejected(self):
        e=FakeEnv();e.tcp=e.ps['red'][:3].copy();self.assertFalse(grade(e)['success'])
    def test_moving_board_reference(self):
        e=FakeEnv()
        for p in e.ps.values():p[:2]+=[.015,-.012]
        self.assertTrue(grade(e)['success'])

if __name__=='__main__':unittest.main()
