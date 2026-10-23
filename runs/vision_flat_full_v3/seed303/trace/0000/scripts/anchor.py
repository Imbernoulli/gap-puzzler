"""RGB-driven motion and CAD grasp search. No simulator/evaluator imports."""
import json
import math
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from puzzler import model as m

MOTION_SCALE=1.
def params(path):
    global MOTION_SCALE
    p=json.loads((Path(path).resolve().parent.parent/'params.json').read_text())
    MOTION_SCALE=p.get('motion_scale',1.)
    return p
def pose(p,q):
    return dict(position=dict(zip('xyz',map(float,p))),rotation=q)
def qarr(q):return np.array([q[k] for k in ['x','y','z','w']])
def qdict(q):return dict(zip(['x','y','z','w'],map(float,q)))
def state(ctx,hints=None):return ctx.tool('vision.observe',hints=hints)
def move(ctx,p,q,arm=1,steps=180,cartesian=False):
    if cartesian:
        result=ctx.tool('puzzle.plan_path',position=list(map(float,p)),rotation=q,arm_id=arm)
        if not result['feasible']:raise RuntimeError('Continuous Cartesian planning refused '+str(result['errors'][-1]))
        path=[];joints=np.asarray(result['path'])
        for a,b in zip(joints[:-1],joints[1:]):
            count=max(1,int(np.ceil(np.max(np.abs(b-a))/(.018*MOTION_SCALE))))
            path.extend({'positions':(a+(b-a)*u).tolist()} for u in np.linspace(0,1,count+1)[1:])
        ctx.tool('robot.execute_trajectory',trajectory={'waypoints':path},arm_id=arm,max_steps_per_waypoint=2)
        return {'outcome':'reached','plan':result}
    plan=ctx.tool('puzzle.plan_pose',position=list(map(float,p)),rotation=q,arm_id=arm)
    if plan['position_error_m']>.008 or plan['rotation_error_rad']>.12:
        raise RuntimeError('Full-pose planning refused '+str(plan))
    a=np.array(plan['current']);b=np.array(plan['joints'])
    count=max(20,min(120,int(np.max(np.abs(b-a))/.018)))
    count=max(14,int(count/MOTION_SCALE))
    path=[]
    for u in np.linspace(0,1,count):
        t=u*u*(3-2*u);path.append({'positions':(a+(b-a)*t).tolist()})
    ctx.tool('robot.execute_trajectory',trajectory={'waypoints':path},arm_id=arm,max_steps_per_waypoint=2)
    return {'outcome':'reached','plan':plan}
def grip(ctx,arm,width):ctx.tool('robot.set_grip',arm_id=arm,width_m=width,ramp_steps=18,settle_steps=15)
def frame(ctx,heading,arm,approach=None):
    kwargs=dict(close_heading_deg=float(heading),arm_id=arm)
    if approach is not None:kwargs['approach']=dict(zip('xyz',map(float,approach)))
    return ctx.tool('robot.grasp_frame',**kwargs)['rotation']
def hand(ctx,arm):
    h=ctx.tool('robot.get_ee_pose',arm_id=arm)
    h=h.get('pose',h)
    return np.array([h['position'][k] for k in 'xyz']),h['rotation']

def anchor(ctx,p):
    arm=int(p.get('support_arm',0))
    if p.get('safe_anchor'):
        tcp,q0=hand(ctx,arm)
        if tcp[2]<.865:move(ctx,[tcp[0],tcp[1],.865],q0,arm)
    s=state(ctx);b=np.array(s['poses']['board']);R=Rotation.from_quat(b[3:]).as_matrix()
    grasp=b[:3]+R@np.array([-.078,.145 if arm==0 else -.145,.020])
    q=frame(ctx,-90 if arm==0 else 90,arm)
    if not p.get('safe_anchor'):grip(ctx,arm,.008)
    move(ctx,grasp+[0,0,.09],q,arm)
    if p.get('safe_anchor'):grip(ctx,arm,.008)
    if p.get('anchor',True):
        move(ctx,grasp,q,arm,steps=100)
    return dict(route='ready',initial_board=b.tolist(),hand=hand(ctx,arm)[0].tolist())

def plan(ctx,name,p,arm=1):
    s=state(ctx);poses=s['poses'];b=np.array(poses['board']);body=np.array(poses[name])
    if set(m.CELLS)-set(poses):
        raise RuntimeError('Cannot plan grasp with unobserved obstacles: '+str(sorted(set(m.CELLS)-set(poses))))
    R=Rotation.from_quat(body[3:]).as_matrix();Rb=Rotation.from_quat(b[3:]).as_matrix()
    from puzzler.vision_observer import goals
    target_center,target_R=goals(p.get('mode','flat'),p.get('pyramid_plan','pyramid_robot6_plan.json'))[name]
    # Footprint is solved, while grasp candidates are geometrically outside the part.
    local=m.local_beads(name)
    yaw=math.degrees(Rotation.from_quat(body[3:]).as_euler('xyz')[2])
    rotations=[target_R]
    if p.get('shape_symmetry'):
        for k in range(4):
            for flip in (False,True):
                symmetry=m.rotation(k*np.pi/2)@(np.diag([1.,-1.,-1.]) if flip else np.eye(3))
                transformed=local@symmetry.T
                if np.max(np.min(np.linalg.norm(transformed[:,None]-local[None,:],axis=2),axis=1))<1e-7:
                    candidate=target_R@symmetry
                    if not any(np.allclose(candidate,r) for r in rotations):rotations.append(candidate)
    if 'target_normal' in p:
        normal=np.asarray(p['target_normal'],dtype=float)
        normal=normal/np.linalg.norm(normal)
        rotations=[r for r in rotations if np.dot(r[:,2],normal)>.99]
        if not rotations:raise ValueError(f'No rigid shape symmetry matches target normal for {name}')
    shape_local=local.copy()
    pairs=p.get('grasp_pairs',[])
    if pairs:
        for i,j in pairs:
            if abs(np.linalg.norm(shape_local[i]-shape_local[j])-m.PITCH)>1e-6:
                raise ValueError(f'Grasp pair {(i,j)} must be adjacent beads')
        local=np.concatenate((local,[shape_local[[i,j]].mean(axis=0) for i,j in pairs]))
        p={**p,'grasp_indices':list(range(len(shape_local),len(local)))}
    obstacles=np.concatenate([m.local_beads(n)@Rotation.from_quat(np.array(bp)[3:]).as_matrix().T+np.array(bp)[:3]
                              for n,bp in poses.items() if n not in ('board',name)])
    candidates=[]
    for candidate_R in rotations:
      heights=(local@candidate_R.T)[:,2]
      for i,a in enumerate(local):
        if 'grasp_indices' in p and i not in p['grasp_indices']:continue
        headings=p.get('grasp_headings',[90.,0.,270.,180.]) if p.get('grasp_auto') else ([float(p['world_heading'])-yaw] if 'world_heading' in p else ([float(p['grasp_heading'])] if 'grasp_heading' in p else (0.,90.)))
        for heading in headings:
            direction=np.array([math.cos(math.radians(heading)),math.sin(math.radians(heading)),0.])
            neighbours=shape_local
            if i>=len(shape_local):
                neighbours=np.delete(shape_local,pairs[i-len(shape_local)],axis=0)
            delta=neighbours-a
            blocked=sum(.005<abs(d@direction)<p.get('max_grasp_obstacle_distance',float('inf'))
                        and np.linalg.norm(d-(d@direction)*direction)<p.get('neighbor_clearance',.018) for d in delta)
            clearance=float(np.linalg.norm(obstacles-(body[:3]+R@a),axis=1).min()) if p.get('obstacle_grasp') else 0.
            torque=abs(float(a[0]*direction[1]-a[1]*direction[0])) if p.get('grasp_torque') else 0.
            score=(-float(heights[i]),blocked,torque,-clearance,-float(np.linalg.norm(a))) if p.get('mode')=='pyramid' else (blocked,torque,-clearance,-float(np.linalg.norm(a)))
            candidates.append((score,i,heading,candidate_R))
    candidates.sort(key=lambda x:x[0])
    best_cost=float('inf')
    for score,idx,heading,candidate_R in candidates:
      for lean in p.get('grasp_leans',[0.]):
        if score[1 if p.get('mode')=='pyramid' else 0]>0 and p.get('grasp_auto'):continue
        actual=body[:3]+R@local[idx]
        grasp=actual+np.array([p.get('pick_bias',0.),0,p.get('grasp_z',0.)])
        world_heading=heading+yaw if p.get('perceive_yaw',True) else heading
        h=np.radians(world_heading);theta=np.radians(lean)
        approach=np.array([np.sin(h)*np.sin(theta),-np.cos(h)*np.sin(theta),-np.cos(theta)])
        goal_axis=Rb@candidate_R@R.T@approach
        if 'min_target_approach_down' in p and goal_axis[2]>-p['min_target_approach_down']:continue
        q=frame(ctx,world_heading,arm,approach)
        if p.get('grasp_auto'):
            goal_q=qdict(Rotation.from_matrix(Rb@candidate_R@R.T@Rotation.from_quat(qarr(q)).as_matrix()).as_quat())
            goal_p=b[:3]+Rb@target_center+Rb@candidate_R@local[idx]+Rb@candidate_R@R.T@np.array([0.,0.,p.get('grasp_z',0.)])
            cost=0.
            checks=[(goal_p+[0,0,p.get('transport',.10)],goal_q),
                    (grasp+[0,0,p.get('source_hover',.10)],q),
                    (grasp,q),
                    (grasp+[0,0,p.get('lift',.085)],q),
                    (goal_p+[0,0,p.get('release_height',.025)],goal_q)]
            if p.get('source_grasp_only'):checks=[(grasp+[0,0,p.get('source_hover',.10)],q),(grasp,q)]
            for position,rotation in checks:
                check=ctx.tool('puzzle.plan_pose',position=position.tolist(),rotation=rotation,arm_id=arm)
                cost=max(cost,check['position_error_m']+.05*check['rotation_error_rad'])
                if cost>.006:break
            best_cost=min(best_cost,cost)
            if cost>.006:continue
        return dict(s=s,body=body,grasp=grasp,rotation=q,index=idx,target_center=target_center,target_R=candidate_R,heading=heading,lean=lean)
    raise RuntimeError(f'No feasible source/target grasp for {name}: {best_cost}')


def required(ctx, names, hints=None):
    s=state(ctx,hints)
    missing=[n for n in names if n not in s['poses']]
    if missing:raise RuntimeError('RGB perception uncertain: '+str({n:s['detections'][n]['reason'] for n in missing}))
    return s


def inspect_held(ctx,name,prediction,arm):
    """Change viewpoint via known robot motion when a held part is occluded.

    A rigid-grasp prediction seeds the fit; only new RGB evidence can return
    a pose. This does not attach the part or consult a grasp/contact oracle.
    """
    measured=state(ctx,{name:prediction.tolist()})
    if all(n in measured['poses'] for n in ('board',name)):return measured
    # Try a higher inspection pose first, then bounded wrist yaw changes.
    tcp,q=hand(ctx,arm)
    for dz,yaw in [(.10,0.),(0.,60.),(0.,-120.)]:
        delta=Rotation.from_euler('z',yaw,degrees=True).as_matrix()
        new_q=qdict(Rotation.from_matrix(delta@Rotation.from_quat(qarr(q)).as_matrix()).as_quat())
        target=tcp+[0,0,dz]
        next_prediction=np.r_[target+delta@(prediction[:3]-tcp),
                              (Rotation.from_matrix(delta)*Rotation.from_quat(prediction[3:])).as_quat()]
        try:move(ctx,target,new_q,arm)
        except RuntimeError:continue
        prediction=next_prediction;tcp,q=hand(ctx,arm)
        measured=state(ctx,{name:prediction.tolist()})
        if all(n in measured['poses'] for n in ('board',name)):return measured
    raise RuntimeError('RGB perception remains uncertain after active inspection: '+name)


def place(ctx,name,p):
    """Detect, choose source arm, grasp, remeasure, carry, release and remeasure."""
    p={**p,**p.get('pieces',{}).get(name,{})}
    s=required(ctx,['board',name])
    # Arm selection follows the measured source position, not an initial layout.
    arm=0 if s['poses'][name][1] >= 0 else 1
    tcp,q0=hand(ctx,arm)
    if tcp[2]<.865:move(ctx,[tcp[0],tcp[1],.865],q0,arm)
    anchor(ctx,{**p,'support_arm':1-arm})
    pl=plan(ctx,name,p,arm);g=pl['grasp'];q=pl['rotation']
    grip(ctx,arm,p.get('open_width',.055))
    move(ctx,g+[0,0,p.get('source_hover',.11)],q,arm)
    move(ctx,g,q,arm)
    grip(ctx,arm,p.get('close_width',0.))
    lift=p.get('lift',.085)
    move(ctx,g+[0,0,lift],q,arm)
    prediction=pl['body'].copy();prediction[2]+=lift
    measured=inspect_held(ctx,name,prediction,arm)
    now=np.array(measured['poses'][name])
    rise=float(now[2]-pl['body'][2])
    if rise<.025:
        grip(ctx,arm,.055)
        return dict(route='retry',failure='visually_measured_grasp_miss',piece=name,rise_m=rise)
    tcp,qnow=hand(ctx,arm)
    b=np.array(measured['poses']['board']);Rb=Rotation.from_quat(b[3:]).as_matrix()
    desired_R=Rb@pl['target_R']
    delta=desired_R@Rotation.from_quat(now[3:]).as_matrix().T
    qtarget=qdict(Rotation.from_matrix(delta@Rotation.from_quat(qarr(qnow)).as_matrix()).as_quat())
    target=b[:3]+Rb@pl['target_center']
    target_tcp=target+delta@(tcp-now[:3])
    transport=p.get('transport',.09)
    move(ctx,target_tcp+[0,0,transport],qtarget,arm)
    prediction=np.r_[target+[0,0,transport],Rotation.from_matrix(desired_R).as_quat()]
    carried=inspect_held(ctx,name,prediction,arm)
    body=np.array(carried['poses'][name]);b=np.array(carried['poses']['board'])
    Rb=Rotation.from_quat(b[3:]).as_matrix();desired_R=Rb@pl['target_R']
    tcp,qnow=hand(ctx,arm)
    correction=desired_R@Rotation.from_quat(body[3:]).as_matrix().T
    qtarget=qdict(Rotation.from_matrix(correction@Rotation.from_quat(qarr(qnow)).as_matrix()).as_quat())
    target_tcp=b[:3]+Rb@pl['target_center']+correction@(tcp-body[:3])
    move(ctx,target_tcp+[0,0,p.get('release_height',.028)],qtarget,arm)
    grip(ctx,arm,.055)
    move(ctx,target_tcp+[0,0,.10],qtarget,arm)
    ctx.tool('robot.wait_steps',steps=50)
    prediction=np.r_[b[:3]+Rb@pl['target_center'],Rotation.from_matrix(desired_R).as_quat()]
    after=required(ctx,['board',name],{name:prediction.tolist()})
    error=after['assessment']['bead_error_m'][name]
    placed=error is not None and error<.003
    return dict(route='placed' if placed else 'retry',piece=name,visual_error_m=error,
                visual_rise_m=rise,failure='' if placed else 'visual_goal_residual',
                observation_source=after['observation_source'])


def finish(ctx,p):
    for arm in (1,0):
        tcp,q=hand(ctx,arm)
        grip(ctx,arm,.055)
        if tcp[2]<.9:move(ctx,tcp+[0,0,.05],q,arm)
        ctx.tool('robot.go_home',arm_id=arm)
    ctx.tool('robot.wait_steps',steps=100)
    names=p.get('diagnostic_subset') or list(m.CELLS)
    s=required(ctx,['board',*names])
    ctx.tool('robot.wait_steps',steps=50)
    after=required(ctx,['board',*names])
    # Observable stability is measured from repeated images, never body velocity.
    from scipy.optimize import linear_sum_assignment
    displacement={}
    for n in names:
        a=np.array(s['poses'][n]);b=np.array(after['poses'][n]);local=m.local_beads(n)
        aa=local@Rotation.from_quat(a[3:]).as_matrix().T+a[:3]
        bb=local@Rotation.from_quat(b[3:]).as_matrix().T+b[:3]
        cost=np.linalg.norm(aa[:,None]-bb[None,:],axis=2);ii,jj=linear_sum_assignment(cost)
        displacement[n]=float(cost[ii,jj].max())
    good=all(after['assessment']['bead_error_m'][n]<.003 and displacement[n]<.0015 for n in names)
    return dict(route='complete' if good else 'failed',visual_assessment=after['assessment'],
                displacement_m=displacement,diagnostic_subset=p.get('diagnostic_subset',[]))


def run(ctx):
    p=params(__file__)
    return anchor(ctx,p)
