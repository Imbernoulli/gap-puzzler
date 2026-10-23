import json
import numpy as np
from scipy.spatial.transform import Rotation
from puzzler.task import build,Variant
from puzzler.tools import register
from puzzler.controller import frame,qarr,qdict
from puzzler import model as m
from tools.preflight import DirectBus,Registry
from robosimstudio_policy_agent.robot_tools import RobotTools
from puzzler.task import placement,poses

env=build(Variant(mode='pyramid',pyramid_plan='pyramid_robot6_plan.json',embodiment='yam_bimanual_precision20v1'));env.reset();env.run(65)
bus=DirectBus();ctx=Registry();register(ctx,env,bus);ctx.functions['robot.grasp_frame']=RobotTools(env,bus).grasp_frame
ps=poses(env);b=ps['board'];body=ps['red'];R=Rotation.from_quat(body[3:]).as_matrix();Rb=Rotation.from_quat(b[3:]).as_matrix();c,Rt=placement(Variant(mode='pyramid',pyramid_plan='pyramid_robot6_plan.json'),'red')
rows=[]
for idx in [4,0,3]:
 for heading in [0,45,90,135,180,225,270,315]:
  d=np.array([np.cos(np.radians(heading)),np.sin(np.radians(heading)),0])
  delta=m.local_beads('red')-m.local_beads('red')[idx]
  if any(.005<abs(x@d)<.030 and np.linalg.norm(x-(x@d)*d)<.016 for x in delta):continue
  for lean in [0,-30,30,-45,45,-60,60,-75,75]:
   h=np.radians(heading);t=np.radians(lean);app=np.array([np.sin(h)*np.sin(t),-np.cos(h)*np.sin(t),-np.cos(t)])
   goal_app=Rb@Rt@R.T@app
   if goal_app[2]>-.2:continue
   q=frame(ctx,heading,1,app);g=body[:3]+R@m.local_beads('red')[idx]+[0,0,.004]
   gp=b[:3]+Rb@c+Rb@Rt@m.local_beads('red')[idx]+Rb@Rt@R.T@np.array([0,0,.004]);gq=qdict(Rotation.from_matrix(Rb@Rt@R.T@Rotation.from_quat(qarr(q)).as_matrix()).as_quat())
   checks=[]
   for point,rot in [(gp+[0,0,.03],gq),(gp+[0,0,.003],gq),(g+[0,0,.05],q),(g,q)]:
    v=ctx.tool('puzzle.plan_pose',position=point.tolist(),rotation=rot,arm_id=1);checks.append([v['position_error_m'],v['rotation_error_rad'],v['joint_limit_margin_rad']])
    if v['position_error_m']>.002 or v['rotation_error_rad']>.025:break
   if len(checks)==4 and max(v[0] for v in checks)<.002 and max(v[1] for v in checks)<.025:
    row=dict(index=idx,heading=heading,lean=lean,goal_approach=goal_app.tolist(),checks=checks);rows.append(row);print(row,flush=True)
json.dump(rows,open('results/red_grasp_scan.json','w'),indent=2)
