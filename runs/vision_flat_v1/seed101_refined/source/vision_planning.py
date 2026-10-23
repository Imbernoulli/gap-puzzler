"""Robot-encoder and kinematic-model planning only; no object-state reads."""
import numpy as np

def register(registry,env,bus):
    pose_cache={0:[],1:[]}
    def plan_pose(position:list,rotation:dict,arm_id:int=0):
        """RSS full-pose IK using live, nearby verified and home seeds; no state writes."""
        def solve():
            ik=env.arm('left' if arm_id==0 else 'right')
            seed=env.state.joint_q.numpy().copy();q=np.array([rotation[k] for k in ['x','y','z','w']])
            def distance(entry):
                p0,q0,_=entry
                angle=2*np.arccos(np.clip(abs(np.dot(q0,q))/(np.linalg.norm(q0)*np.linalg.norm(q)),0,1))
                return np.linalg.norm(np.asarray(position)-p0)+.05*angle
            nearby=sorted(pose_cache[arm_id],key=distance)[:3]
            seeds=[('live',seed.copy())]
            for _,_,joints in nearby:
                ss=seed.copy();ss[ik.arm_coords]=joints;seeds.append(('nearby_verified',ss))
            ss=seed.copy();ss[ik.arm_coords]=ik._home_q;seeds.append(('home',ss))
            best=None;attempts=0
            for label,ss in seeds:
                attempts+=1
                sol=ik.solve_q_full(ss,position,q)
                pe,re=ik.pose_errors(sol,position,q)
                cost=pe+.05*re
                if best is None or cost<best[0]:best=(cost,sol,pe,re,label)
                if pe<.0001 and re<.001:break
            cost,sol,pe,re,label=best
            lower=ik.model.joint_limit_lower.numpy()[ik.arm_dofs]
            upper=ik.model.joint_limit_upper.numpy()[ik.arm_dofs]
            joint_margin=float(np.minimum(sol[ik.arm_coords]-lower,upper-sol[ik.arm_coords]).min())
            if cost<.006:
                pose_cache[arm_id].append((np.asarray(position).copy(),q.copy(),sol[ik.arm_coords].copy()))
                pose_cache[arm_id]=pose_cache[arm_id][-32:]
            return dict(joints=sol[ik.arm_coords].tolist(),current=seed[ik.arm_coords].tolist(),position_error_m=pe,rotation_error_rad=re,
                        seed_kind=label,seed_attempts=attempts,joint_limit_margin_rad=joint_margin)
        return bus.call(solve)
    def plan_path(position:list,rotation:dict,arm_id:int=0):
        """Continuous full-pose Cartesian IK chain; no scene-state mutation."""
        def solve():
            from scipy.spatial.transform import Rotation,Slerp
            ik=env.arm('left' if arm_id==0 else 'right')
            seed=env.state.joint_q.numpy().copy()
            start_p,start_q=ik.ee_pose(env.state)
            target=np.asarray(position);target_q=np.array([rotation[k] for k in ['x','y','z','w']])
            angle=(Rotation.from_quat(start_q).inv()*Rotation.from_quat(target_q)).magnitude()
            count=max(2,int(np.ceil(np.linalg.norm(target-start_p)/.010)),int(np.ceil(angle/.06)))
            fractions=np.linspace(0,1,count+1)
            orientations=Slerp([0,1],Rotation.from_quat([start_q,target_q]))(fractions).as_quat()
            path=[seed[ik.arm_coords].tolist()];errors=[]
            for u,q in zip(fractions[1:],orientations[1:]):
                point=(1-u)*start_p+u*target
                solution=ik.solve_q_full(seed,point,q);pe,re=ik.pose_errors(solution,point,q)
                jump=float(np.max(np.abs(solution[ik.arm_coords]-seed[ik.arm_coords])))
                errors.append(dict(fraction=float(u),position_error_m=pe,rotation_error_rad=re,joint_jump_rad=jump))
                if pe>.004 or re>.06 or jump>.5:
                    return dict(feasible=False,path=[],errors=errors)
                seed=solution;path.append(seed[ik.arm_coords].tolist())
            return dict(feasible=True,path=path,errors=errors)
        return bus.call(solve)
    registry.register_callable('puzzle.plan_pose',plan_pose,summary='RSS native full-pose IK with verified nearby and home restarts, no state mutation.',tags=('planning',))
    registry.register_callable('puzzle.plan_path',plan_path,summary='Continuous full-pose Cartesian IK chain, no collision-free guarantee and no state writes.',tags=('planning',))
