"""Reusable model-based skills. Only robot.* tools change the world."""
import json
import math
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from puzzler import model as m

def params(path):return json.loads((Path(path).resolve().parent.parent/'params.json').read_text())
def pose(p,q):
    return dict(position=dict(zip('xyz',map(float,p))),rotation=q)
def qarr(q):return np.array([q[k] for k in ['x','y','z','w']])
def qdict(q):return dict(zip(['x','y','z','w'],map(float,q)))
def state(ctx):return ctx.tool('puzzle.observe')
def move(ctx,p,q,arm=1,steps=180):
    ctx.tool('robot.go_to_pose',pose=pose(p,q),arm_id=arm,max_steps=steps)
def grip(ctx,arm,width):ctx.tool('robot.set_grip',arm_id=arm,width_m=width,ramp_steps=18,settle_steps=15)
def frame(ctx,heading,arm):return ctx.tool('robot.grasp_frame',close_heading_deg=float(heading),arm_id=arm)['rotation']
def hand(ctx,arm):
    h=ctx.tool('robot.get_ee_pose',arm_id=arm)
    h=h.get('pose',h)
    return np.array([h['position'][k] for k in 'xyz']),h['rotation']

def anchor(ctx,p):
    s=state(ctx);b=np.array(s['poses']['board']);R=Rotation.from_quat(b[3:]).as_matrix()
    grasp=b[:3]+R@np.array([-.12,.085,.012])
    yaw=math.degrees(Rotation.from_quat(b[3:]).as_euler('xyz')[2])
    q=frame(ctx,yaw,0)
    grip(ctx,0,.05)
    move(ctx,grasp+[0,0,.10],q,0)
    if p.get('anchor',True):
        move(ctx,grasp,q,0);grip(ctx,0,.015)
    return dict(route='ready',initial_board=b.tolist(),hand=hand(ctx,0)[0].tolist())

def plan(ctx,name,p):
    s=state(ctx);poses=s['poses'];b=np.array(poses['board']);body=np.array(poses[name])
    R=Rotation.from_quat(body[3:]).as_matrix();Rb=Rotation.from_quat(b[3:]).as_matrix()
    occupied=[c for n,cells in m.CELLS.items() if n not in m.MISSING for c in cells]
    sol=m.solve(occupied)
    if sol is None:raise RuntimeError('No exact cover for observed challenge')
    # Footprint is solved, while grasp candidates are geometrically outside the part.
    local=m.local_beads(name)
    # Choose a terminal bead, with no immediate neighbour along the jaw-closing axis.
    best=None
    for i,a in enumerate(local):
        for heading in (0.,90.):
            direction=np.array([math.cos(math.radians(heading)),math.sin(math.radians(heading)),0.])
            delta=local-a
            blocked=sum(abs(d@direction)>.005 and np.linalg.norm(d-(d@direction)*direction)<.018 for d in delta)
            score=(blocked, -float(np.linalg.norm(a)))
            if best is None or score<best[0]:best=(score,i,heading)
    _,idx,heading=best
    actual=body[:3]+R@local[idx]
    yaw=math.degrees(Rotation.from_quat(body[3:]).as_euler('xyz')[2])
    q=frame(ctx,heading+yaw,1)
    grasp=actual+np.array([p.get('pick_bias',0.)+s['grasp_bias'],0,p.get('grasp_z',0.)])
    if not p.get('perceive_yaw',True):q=frame(ctx,heading,1)
    return dict(s=s,body=body,grasp=grasp,rotation=q,index=idx,solution=sol[name],heading=heading)

def place(ctx,name,p):
    pl=plan(ctx,name,p);g=pl['grasp'];q=pl['rotation']
    grip(ctx,1,p.get('open_width',.055))
    move(ctx,g+[0,0,.11],q)
    move(ctx,g,q,steps=220)
    grip(ctx,1,p.get('close_width',.012))
    move(ctx,g+[0,0,p.get('lift',.085)],q,steps=240)
    s=state(ctx);now=np.array(s['poses'][name]);start=pl['body']
    rise=float(now[2]-start[2])
    if rise<.025:return dict(route='retry',failure='grasp_miss',rise=rise,piece=name)
    tcp,qnow=hand(ctx,1)
    b=np.array(s['poses']['board']);Rb=Rotation.from_quat(b[3:]).as_matrix()
    # The solver's quarter turn maps the native row/column shape. Since rows = -x
    # and columns = -y, the same right-angle rotation applies in the physical plane.
    k=pl['solution']['turns'];desired_R=Rb@m.rotation(k*math.pi/2)
    actual_R=Rotation.from_quat(now[3:]).as_matrix()
    delta_R=desired_R@actual_R.T
    qtarget=qdict(Rotation.from_matrix(delta_R@Rotation.from_quat(qarr(qnow)).as_matrix()).as_quat())
    centers=np.array(pl['solution']['cells'])
    target_local=np.r_[m.xy(centers).mean(axis=0),m.BEAD_Z]
    if p.get('board_feedback',True):target=b[:3]+Rb@target_local
    else:target=m.ORIGIN+m.BOARD_AT+target_local
    # Measure object-to-TCP after lifting, so off-center and shifted grasps are carried correctly.
    offset=(tcp-now[:3]) if p.get('grasp_feedback',True) else (pl['grasp']-pl['body'][:3])
    offset=delta_R@offset
    target_tcp=target+offset
    if p.get('carry_speed',1.)<1.:
        ctx.tool('robot.go_to_pose_cartesian',pose=pose(target_tcp+[0,0,p.get('transport',.10)],qtarget),arm_id=1,speed_scale=p['carry_speed'])
    else:move(ctx,target_tcp+[0,0,p.get('transport',.10)],qtarget,steps=260)
    move(ctx,target_tcp+[0,0,p.get('release_height',.025)],qtarget,steps=240)
    grip(ctx,1,p.get('release_width',.055))
    move(ctx,target_tcp+[0,0,.12],qtarget,steps=200)
    ctx.tool('robot.wait_steps',steps=p.get('settle_steps',45))
    after=state(ctx);error=after['grade']['bead_error_m'][name]
    return dict(route='placed' if error<.004 else 'retry',failure='' if error<.004 else 'placement_error',
                piece=name,error_m=error,rise=rise,board=after['poses']['board'])

def finish(ctx,p):
    for arm in (1,0):
        grip(ctx,arm,.075)
        tcp,q=hand(ctx,arm);move(ctx,tcp+[0,0,.13],q,arm)
    ctx.tool('robot.wait_steps',steps=75)
    g=state(ctx)['grade']
    return dict(route='complete' if g['success'] else 'failed',grade=g)


def run(ctx):
    p=params(__file__)
    return anchor(ctx,p)
