"""Reusable model-based skills. Only robot.* tools change the world."""
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
def state(ctx):return ctx.tool('puzzle.observe')
def move(ctx,p,q,arm=1,steps=180):
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
    R=Rotation.from_quat(body[3:]).as_matrix();Rb=Rotation.from_quat(b[3:]).as_matrix()
    from puzzler.task import placement,Variant
    target_center,target_R=placement(Variant(mode=s.get('mode','flat'),pyramid_plan=s.get('pyramid_plan','pyramid_upright_plan.json')),name)
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
            delta=local-a
            blocked=sum(.005<abs(d@direction)<p.get('max_grasp_obstacle_distance',float('inf'))
                        and np.linalg.norm(d-(d@direction)*direction)<p.get('neighbor_clearance',.018) for d in delta)
            clearance=float(np.linalg.norm(obstacles-(body[:3]+R@a),axis=1).min()) if p.get('obstacle_grasp') else 0.
            score=(-float(heights[i]),blocked,-clearance,-float(np.linalg.norm(a))) if s.get('mode')=='pyramid' else (blocked,-clearance,-float(np.linalg.norm(a)))
            candidates.append((score,i,heading,candidate_R))
    candidates.sort(key=lambda x:x[0])
    best_cost=float('inf')
    for score,idx,heading,candidate_R in candidates:
      for lean in p.get('grasp_leans',[0.]):
        if score[1 if s.get('mode')=='pyramid' else 0]>0 and p.get('grasp_auto'):continue
        actual=body[:3]+R@local[idx]
        grasp=actual+np.array([p.get('pick_bias',0.)+s['grasp_bias'],0,p.get('grasp_z',0.)])
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
                    (grasp+[0,0,.10],q),
                    (goal_p+[0,0,p.get('release_height',.025)],goal_q)]
            if p.get('source_grasp_only'):checks=[(grasp+[0,0,.10],q),(grasp,q)]
            for position,rotation in checks:
                check=ctx.tool('puzzle.plan_pose',position=position.tolist(),rotation=rotation,arm_id=arm)
                cost=max(cost,check['position_error_m']+.05*check['rotation_error_rad'])
                if cost>.006:break
            best_cost=min(best_cost,cost)
            if cost>.006:continue
        return dict(s=s,body=body,grasp=grasp,rotation=q,index=idx,target_center=target_center,target_R=candidate_R,heading=heading,lean=lean)
    raise RuntimeError(f'No feasible source/target grasp for {name}: {best_cost}')

def regrasp(ctx,name,p,donor,target_R):
    """Motor/contact handoff in free air; neither hand attaches the object."""
    receiver=1-donor
    s=state(ctx);body=np.array(s['poses'][name]);board=np.array(s['poses']['board'])
    desired_R=Rotation.from_quat(board[3:]).as_matrix()@target_R
    tcp,q=hand(ctx,donor)
    idx=int(p.get('receive_indices',[3])[0])
    source_R=Rotation.from_quat(body[3:]).as_matrix()
    chosen=None
    for center_value in p.get('handoff_centers',[[.46,0.,1.00],[.50,0.,1.00],[.46,0.,1.08],[.42,0.,.98]]):
      center=np.array(center_value)
      for yaw in p.get('handoff_yaws',[0.,90.,-90.,180.]):
        handoff_R=m.rotation(np.radians(yaw))@desired_R
        delta=handoff_R@source_R.T
        donor_q=qdict(Rotation.from_matrix(delta@Rotation.from_quat(qarr(q)).as_matrix()).as_quat())
        donor_tcp=center+delta@(tcp-body[:3])
        normal=handoff_R[:,2];heading=float(np.degrees(np.arctan2(normal[1],normal[0])))
        receive_q=frame(ctx,heading+p.get('receive_heading_offset',0.),receiver)
        receive_tcp=center+handoff_R@m.local_beads(name)[idx]+[0,0,p.get('receive_grasp_z',.006)]
        checks=[(donor,donor_tcp,donor_q),(receiver,receive_tcp+[0,0,.10],receive_q),(receiver,receive_tcp,receive_q)]
        feasible=True
        for check_arm,position,rotation in checks:
            result=ctx.tool('puzzle.plan_pose',position=position.tolist(),rotation=rotation,arm_id=check_arm)
            if result['position_error_m']>.004 or result['rotation_error_rad']>.06:
                feasible=False;break
        if feasible:chosen=(donor_tcp,donor_q,yaw,center_value);break
      if chosen:break
    if chosen is None:raise RuntimeError('No mutually reachable free-air handoff pose')
    donor_tcp,donor_q,handoff_yaw,center_value=chosen
    move(ctx,donor_tcp,donor_q,donor)
    s=state(ctx);body=np.array(s['poses'][name]);actual_R=Rotation.from_quat(body[3:]).as_matrix()
    beads=m.local_beads(name)@actual_R.T+body[:3]
    candidates=p.get('receive_indices',np.argsort(-beads[:,2]).tolist())
    idx=int(candidates[0])
    # Close perpendicular to the vertical piece plane, leaving its lower beads clear.
    normal=actual_R[:,2];heading=float(np.degrees(np.arctan2(normal[1],normal[0])))
    receive_q=frame(ctx,heading+p.get('receive_heading_offset',0.),receiver)
    receive_tcp=beads[idx]+[0,0,p.get('receive_grasp_z',.006)]
    grip(ctx,receiver,p.get('receive_open_width',.035))
    current,current_q=hand(ctx,receiver)
    if current[2]<1.12:move(ctx,[current[0],current[1],1.12],current_q,receiver)
    move(ctx,receive_tcp+[0,0,.10],receive_q,receiver)
    move(ctx,receive_tcp,receive_q,receiver)
    grip(ctx,receiver,0.)
    before=np.array(state(ctx)['poses'][name])
    grip(ctx,donor,.04)
    donor_tcp,donor_q=hand(ctx,donor)
    away=-Rotation.from_quat(qarr(donor_q)).as_matrix()[:,2]*.12+[0,0,.04]
    move(ctx,donor_tcp+away,donor_q,donor)
    receive_tcp,receive_q=hand(ctx,receiver)
    move(ctx,receive_tcp+[0,0,.04],receive_q,receiver)
    after=np.array(state(ctx)['poses'][name])
    if after[2]-before[2]<.020:
        raise RuntimeError(f'Physical handoff lost {name}: rise={after[2]-before[2]:.5f}')
    anchor(ctx,{**p,'support_arm':donor})
    return receiver,dict(donor=donor,receiver=receiver,bead=idx,verified_rise_m=float(after[2]-before[2]),yaw=handoff_yaw,center=center_value)

def place(ctx,name,p):
    from puzzler.task import staging
    p={**p,**p.get('pieces',{}).get(name,{})}
    arm=staging()[name][2] if p.get('full_task') else 1
    if p.get('full_task'):
        tcp,q0=hand(ctx,arm)
        if tcp[2]<.865:move(ctx,[tcp[0],tcp[1],.865],q0,arm)
        anchor(ctx,{**p,'support_arm':1-arm})
        if not p.get('terminal_grasp'):p={**p,'grasp_heading':90.}
    source_params={**p,**p.get('donor_grasp',{}),'source_grasp_only':True} if p.get('handoff') else p
    pl=plan(ctx,name,source_params,arm);g=pl['grasp'];q=pl['rotation']
    grip(ctx,arm,p.get('open_width',.055))
    move(ctx,g+[0,0,.11],q,arm)
    move(ctx,g,q,arm,steps=140)
    grip(ctx,arm,p.get('close_width',.012))
    move(ctx,g+[0,0,p.get('lift',.085)],q,arm,steps=240)
    s=state(ctx);now=np.array(s['poses'][name]);start=pl['body']
    rise=float(now[2]-start[2])
    if rise<.025:return dict(route='retry',failure='grasp_miss',rise=rise,piece=name)
    handoff_info=None
    if p.get('handoff'):
        arm,handoff_info=regrasp(ctx,name,p,arm,pl['target_R'])
        s=state(ctx);now=np.array(s['poses'][name])
    tcp,qnow=hand(ctx,arm)
    b=np.array(s['poses']['board']);Rb=Rotation.from_quat(b[3:]).as_matrix()
    # The solver's quarter turn maps the native row/column shape. Since rows = -x
    # and columns = -y, the same right-angle rotation applies in the physical plane.
    desired_R=Rb@pl['target_R']
    actual_R=Rotation.from_quat(now[3:]).as_matrix()
    delta_R=desired_R@actual_R.T
    qtarget=qdict(Rotation.from_matrix(delta_R@Rotation.from_quat(qarr(qnow)).as_matrix()).as_quat())
    target_local=pl['target_center']
    if p.get('board_feedback',True):target=b[:3]+Rb@target_local
    else:target=m.ORIGIN+m.BOARD_AT+target_local
    # Measure object-to-TCP after lifting, so off-center and shifted grasps are carried correctly.
    offset=(tcp-now[:3]) if p.get('grasp_feedback',True) else (pl['grasp']-pl['body'][:3])
    offset=delta_R@offset
    target_tcp=target+offset
    if p.get('native_carry',False):
        move(ctx,target_tcp+[0,0,p.get('transport',.10)],qtarget,arm,steps=260)
    elif p.get('carry_speed',1.)<1.:
        carried=ctx.tool('robot.go_to_pose_cartesian',pose=pose(target_tcp+[0,0,p.get('transport',.10)],qtarget),arm_id=arm,speed_scale=p['carry_speed'])
        if carried.get('outcome')!='reached':return dict(route='retry',failure='transport_'+carried.get('outcome','unknown'),motion=carried)
    else:move(ctx,target_tcp+[0,0,p.get('transport',.10)],qtarget,arm,steps=260)
    move(ctx,target_tcp+[0,0,p.get('release_height',.025)],qtarget,arm,steps=240)
    grip(ctx,arm,p.get('release_width',.055))
    retreat=np.array([0.,0.,p.get('retreat',.10)+.01]) if p.get('vertical_retreat') else Rb@pl['target_R']@np.array([0.,0.,p.get('retreat',.10)])+[0,0,.01]
    if p.get('tool_retreat'):retreat=-Rotation.from_quat(qarr(qtarget)).as_matrix()[:,2]*p.get('retreat',.10)+[0,0,.01]
    move(ctx,target_tcp+retreat,qtarget,arm,steps=200)
    ctx.tool('robot.wait_steps',steps=p.get('settle_steps',45))
    after=state(ctx);error=after['grade']['bead_error_m'][name]
    return dict(route='placed' if error<.004 else 'retry',failure='' if error<.004 else 'placement_error',
                piece=name,error_m=error,rise=rise,board=after['poses']['board'],
                grasp_index=pl['index'],grasp_heading=pl['heading'],grasp_lean=pl['lean'],handoff=handoff_info)

def finish(ctx,p):
    for arm in (1,0):
        tcp,q=hand(ctx,arm)
        grip(ctx,arm,.035)
        if tcp[2]<.9:move(ctx,tcp+[0,0,.04],q,arm)
        grip(ctx,arm,.075)
        ctx.tool('robot.go_home',arm_id=arm)
    ctx.tool('robot.wait_steps',steps=p.get('finish_wait',25))
    g=state(ctx)['grade']
    return dict(route='complete' if g['success'] else 'failed',grade=g)


def run(ctx):
    p=params(__file__)
    return place(ctx,'purple',p)
