"""Changing the tool side may only use a proper rigid symmetry of the same part."""
import unittest
import numpy as np
from puzzler import controller,model as m
from puzzler.task import Variant,placement


class Context:
    def tool(self,name,**kwargs):
        if name=='puzzle.observe':
            return dict(mode='pyramid',pyramid_plan='pyramid_robot6_plan.json',grasp_bias=0.,
                        poses={'board':[*map(float,m.ORIGIN+m.BOARD_AT),0.,0.,0.,1.],
                               'cyan':[.695,.27,.7625,0.,0.,0.,1.],
                               'yellow':[.50,.27,.7625,0.,0.,0.,1.]})
        if name=='robot.grasp_frame':return {'rotation':{'x':0.,'y':0.,'z':0.,'w':1.}}
        if name=='puzzle.plan_pose':return dict(position_error_m=0.,rotation_error_rad=0.)
        raise AssertionError(name)


class TestGraspSymmetry(unittest.TestCase):
    def test_outward_normal_preserves_every_bead_with_a_proper_rotation(self):
        chosen=controller.plan(Context(),'cyan',dict(shape_symmetry=True,
            target_normal=[-1.,-1.,0.],grasp_auto=True),arm=0)
        _,original=placement(Variant(mode='pyramid',pyramid_plan='pyramid_robot6_plan.json'),'cyan')
        actual=chosen['target_R'];local=m.local_beads('cyan')
        distances=np.linalg.norm((local@actual.T)[:,None]-(local@original.T)[None,:],axis=2)
        self.assertLess(distances.min(axis=1).max(),1e-10)
        self.assertAlmostEqual(np.linalg.det(actual),1.)
        self.assertGreater(np.dot(actual[:,2],np.array([-1.,-1.,0.])/np.sqrt(2)),.99)

    def test_impossible_normal_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'No rigid shape symmetry'):
            controller.plan(Context(),'cyan',dict(shape_symmetry=True,target_normal=[1.,0.,0.]),arm=0)


if __name__=='__main__':unittest.main()
