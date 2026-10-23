"""Regression tests for the input boundary, not evaluator-based visual success."""
import ast
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from puzzler import model
from puzzler.vision import Camera, detect, estimate, fit_piece
from puzzler.vision_observer import assess
from puzzler.vision_policy import ALLOWED_TOOLS, RestrictedRegistry
from gap_core.tools import ToolRegistry


def cameras():
    # Two simple, independent calibrated views. No simulation is involved.
    K=np.array([[600.,0,320],[0,600.,240],[0,0,1.]])
    out={}
    for name,x in [('top',0.),('side',.2)]:
        T=np.eye(4);T[:3,:3]=np.diag([1.,-1.,-1.]);T[:3,3]=[.5+x,0,1.5]
        out[name]=Camera(name,K,T)
    return out


def pictures(pose):
    cs=cameras();images={}
    centers=model.local_beads('cyan')@Rotation.from_quat(pose[3:]).as_matrix().T+pose[:3]
    for name,c in cs.items():
        im=np.full((480,640,3),85,np.uint8)
        yy,xx=np.indices((480,640));rays=c.rays(np.c_[xx.ravel(),yy.ravel()])
        for center in centers:
            delta=center-c.camera_to_world[:3,3]
            mask=(np.linalg.norm(np.cross(rays,delta),axis=1)<model.RADIUS).reshape(480,640)
            im[mask]=[round(v*255) for v in model.COLORS['cyan']]
        images[name]=im
    return images,cs


class VisionContractTests(unittest.TestCase):
    def test_ik_seed_reads_only_robot_encoder_slices(self):
        from types import SimpleNamespace
        from puzzler.vision_planning import robot_seed
        class Static:
            def __init__(self,a):self.a=np.array(a)
            def numpy(self):return self.a
        class Encoders:
            def __init__(self):self.reads=[]
            def __getitem__(self,key):
                self.reads.append(key)
                if not isinstance(key,slice) or key.start>=4:raise AssertionError('non-robot read')
                return Static([key.start+.1])
            def numpy(self):raise AssertionError('full scene read')
        q=Encoders();env=SimpleNamespace(
            model=SimpleNamespace(joint_coord_count=11,joint_type=Static([1,1,0,0,4]),joint_q_start=Static([0,1,2,3,4,11])),
            handles=SimpleNamespace(arms={'left':SimpleNamespace(arm_coords=(0,1),gripper_coords=(2,3))}),
            state=SimpleNamespace(joint_q=q))
        seed=robot_seed(env)
        np.testing.assert_array_equal(seed[:4],[.1,1.1,2.1,3.1])
        np.testing.assert_array_equal(seed[4:],[0,0,0,0,0,0,1])
        self.assertEqual(len(q.reads),4)

    def test_sensor_refuses_renderer_depth_or_instance_ids(self):
        from types import SimpleNamespace
        from puzzler.vision_observer import RGBSensor
        sensor=object.__new__(RGBSensor)
        sensor.env=SimpleNamespace(state=object(),step_count=0,pipeline=SimpleNamespace(control_hz=50))
        sensor.renderer=SimpleNamespace(render=lambda state:{'top':{'rgb':np.zeros((2,2,3),np.uint8),'seg':np.ones((2,2))}})
        with self.assertRaisesRegex(ValueError,'undeclared channel'):sensor.capture()

    def test_active_inspection_uses_explicit_arm_and_requires_new_evidence(self):
        from puzzler.vision_controller import inspect_held
        prediction=np.array([.5,.1,.85,0,0,0,1.])
        observed={'poses':{'cyan':prediction.tolist(),'board':[.5,0,.753,0,0,0,1]}}
        class Context:
            count=0
            def tool(self,name,**kwargs):
                if name=='vision.observe':
                    self.count+=1
                    return {'poses':{}} if self.count==1 else observed
                if name=='robot.get_ee_pose':
                    return {'position':dict(x=.5,y=.1,z=.9),'rotation':dict(x=1.,y=0.,z=0.,w=0.)}
                raise AssertionError(name)
        with patch('puzzler.vision_controller.move') as moved:
            result=inspect_held(Context(),'cyan',prediction,arm=1)
        self.assertIs(result,observed)
        self.assertEqual(moved.call_args.args[3],1)

    def test_active_inspection_never_returns_blind_pose_prediction(self):
        from puzzler.vision_controller import inspect_held
        class Context:
            def tool(self,name,**kwargs):
                if name=='vision.observe':return {'poses':{}}
                if name=='robot.get_ee_pose':return {'position':dict(x=.5,y=.1,z=.9),'rotation':dict(x=1.,y=0.,z=0.,w=0.)}
                raise AssertionError(name)
        with patch('puzzler.vision_controller.move'),self.assertRaisesRegex(RuntimeError,'remains uncertain'):
            inspect_held(Context(),'cyan',np.array([.5,.1,.85,0,0,0,1.]),arm=0)

    def test_replayed_rgb_drives_identical_grasp_plan_with_changed_hidden_state(self):
        from puzzler.vision import rig_specs,calibration
        from puzzler.vision_controller import plan
        path=Path(__file__).parent/'fixtures/vision_initial_rgb.npz'
        images=dict(np.load(path));cs=calibration(rig_specs())
        class Context:
            def __init__(self,observed):self.observed=observed;self.calls=[]
            def tool(self,name,**kwargs):
                self.calls.append((name,kwargs))
                if name=='vision.observe':return self.observed
                if name=='robot.grasp_frame':return {'rotation':{'x':1.,'y':0.,'z':0.,'w':0.}}
                if name=='puzzle.plan_pose':return {'position_error_m':0.,'rotation_error_rad':0.}
                raise AssertionError('unexpected tool '+name)
        with patch('puzzler.task.poses',side_effect=AssertionError('truth read')),patch('puzzler.task.grade',side_effect=AssertionError('grade read')):
            with patch.dict('puzzler.task.CURRENT',{'env':object(),'variant':'hidden state A'},clear=True):
                a=Context(estimate(images,cs));pa=plan(a,'cyan',{'grasp_auto':True},0)
            with patch.dict('puzzler.task.CURRENT',{'env':object(),'variant':'hidden state B, different object poses and friction'},clear=True):
                b=Context(estimate(images,cs));pb=plan(b,'cyan',{'grasp_auto':True},0)
        np.testing.assert_array_equal(pa['grasp'],pb['grasp'])
        self.assertEqual(pa['rotation'],pb['rotation'])
        self.assertEqual(a.calls,b.calls)

    def test_replayed_pixels_ignore_hidden_evaluator(self):
        images,cs=pictures(np.array([.5,0.,.8,0.,0.,0.,1.]))
        # No task/evaluator reader may be consulted by image estimation.
        with patch('puzzler.task.poses',side_effect=AssertionError('truth read')), patch('puzzler.task.grade',side_effect=AssertionError('grade read')):
            a=estimate(images,cs)
            with patch.dict('puzzler.task.CURRENT',{'variant':'different hidden physics','env':object()},clear=True):
                b=estimate(images,cs)
        self.assertEqual(json.dumps(a,sort_keys=True),json.dumps(b,sort_keys=True))

    def test_feasible_hover_cannot_hide_an_unreachable_source_grasp(self):
        from puzzler.vision import rig_specs,calibration
        from puzzler.vision_controller import plan
        images=dict(np.load(Path(__file__).parent/'fixtures/vision_initial_rgb.npz'))
        observed=estimate(images,calibration(rig_specs()))
        class Context:
            refused=0
            def tool(self,name,**kwargs):
                if name=='vision.observe':return observed
                if name=='robot.grasp_frame':return {'rotation':{'x':1.,'y':0.,'z':0.,'w':0.}}
                if name=='puzzle.plan_pose':
                    x,y,z=kwargs['position']
                    unreachable=y>.20 and z<.80
                    self.refused+=int(unreachable)
                    return {'position_error_m':.02 if unreachable else 0.,'rotation_error_rad':0.}
                raise AssertionError(name)
        ctx=Context()
        with self.assertRaisesRegex(RuntimeError,'No feasible source/target grasp'):
            plan(ctx,'cyan',{'grasp_auto':True},0)
        self.assertGreater(ctx.refused,0)

    def test_two_views_recover_changed_height_and_xy(self):
        pose=np.array([.535,-.021,.87,0.,0.,0.,1.])
        images,cs=pictures(pose)
        masks={n:detect(im)['cyan'] for n,im in images.items()}
        fitted=fit_piece('cyan',masks,cs,previous=[.53,-.02,.85,0,0,0,1])
        self.assertTrue(fitted['visible'],fitted)
        self.assertLess(np.linalg.norm(np.array(fitted['pose'])[:3]-pose[:3]),.003)

    def test_missing_views_never_fall_back_to_seed(self):
        masks={n:np.zeros((480,640),np.uint8) for n in cameras()}
        result=fit_piece('cyan',masks,cameras(),previous=[0,0,.8,0,0,0,1])
        self.assertFalse(result['visible'])
        self.assertNotIn('pose',result)

    def test_evaluator_tools_blocked_even_after_late_registration(self):
        source=ToolRegistry()
        source.register_callable('vision.observe',lambda:{'pixels':True},summary='sensor')
        source.register_callable('sim.get_object_pose',lambda: (_ for _ in ()).throw(AssertionError('leak')),summary='truth')
        reg=RestrictedRegistry(source)
        reg.register_callable('sim.get_object_pose',lambda:{'leak':True},summary='late truth')
        with self.assertRaises(KeyError):reg.invoke('sim.get_object_pose')
        self.assertEqual(set(reg.runtime_tools()),{'vision.observe'})
        self.assertEqual(reg.invoke('vision.observe'),{'pixels':True})

    def test_unobserved_piece_cannot_pass_visual_goal_check(self):
        result=assess({'poses':{}},{'cyan':(np.zeros(3),np.eye(3))})
        self.assertFalse(result['goal_geometry_consistent'])
        self.assertIsNone(result['bead_error_m']['cyan'])

    def test_controller_and_estimator_have_no_task_or_simulator_imports(self):
        root=Path(__file__).resolve().parents[1]
        for filename in ['vision.py','vision_controller.py','vision_observer.py','vision_planning.py']:
            tree=ast.parse((root/'puzzler'/filename).read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.ImportFrom):
                    self.assertNotIn(node.module,('puzzler.task','task'),filename)
            if filename!='vision_observer.py':
                self.assertNotIn('CURRENT',(root/'puzzler'/filename).read_text())


if __name__=='__main__':unittest.main()
