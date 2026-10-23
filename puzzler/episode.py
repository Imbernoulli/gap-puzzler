import argparse
from dataclasses import asdict,replace
import hashlib,json,os,time,traceback
from pathlib import Path
import numpy as np
from . import task,tools

def run(graph,out,seed=0,nominal=False,max_steps=15000,mode='flat',motion='osc',observation='oracle',scattered=False):
    from .policy import VerifiedGraph
    from robosimstudio_bench.run.runner import rollout
    d=Path(out);d.mkdir(parents=True,exist_ok=True)
    v=task.Variant(seed=seed,mode=mode) if nominal else task.sample(seed,mode)
    graph_params=json.loads((Path(graph)/'params.json').read_text())
    v=replace(v,scattered=scattered,pyramid_plan=graph_params.get('pyramid_plan',v.pyramid_plan),
              embodiment=graph_params.get('embodiment',v.embodiment),
              preset_pieces=tuple(graph_params.get('diagnostic_preset_pieces',())))
    if v.embodiment!='yam_bimanual':
        from .hardware import register
        register(v.embodiment)
    source_paths=[*sorted((task.m.ROOT/'puzzler').glob('*.py')),*sorted(Path(graph).rglob('*.py')),
                  Path(graph)/'params.json',*sorted((task.m.ROOT/'assets').glob('*.obj')),
                  task.m.ROOT/'assets'/v.pyramid_plan]
    if v.embodiment!='yam_bimanual':source_paths.extend(sorted((task.m.ROOT/'assets').glob('*.xml')))
    source_hashes={str(p.resolve().relative_to(task.m.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    if observation=='rgb':
        for p in sorted((task.m.ROOT/'puzzler').glob('vision*.py')):
            target=d/'source'/p.name;target.parent.mkdir(exist_ok=True);target.write_bytes(p.read_bytes())
    start=time.perf_counter();env=task.build(v,max_steps=max_steps)
    samples=[];checks=[];events=[]
    if observation=='rgb':
        from .vision_policy import VisionGraph
        Policy=VisionGraph
    else:Policy=VerifiedGraph
    class Traced(Policy):
        def _on_graph_node_start(self,name,success,generation=None):
            events.append(dict(node=name,event='start',step=int(env.step_count)))
            return super()._on_graph_node_start(name,success,generation)
        def _on_graph_node_end(self,name,success,generation=None):
            events.append(dict(node=name,event='end',ok=bool(success),step=int(env.step_count)))
            return super()._on_graph_node_end(name,success,generation)
    policy_options=dict(visual_mode=mode,visual_plan=v.pyramid_plan,observation_dir=d/'rgb') if observation=='rgb' else dict(task_tools=tools.register)
    policy=Traced(env,graph=str(Path(graph).resolve()),roll='held',motion=motion,
                  trace_dir=str(d/'trace'),bus_timeout=600.,settle_steps=150,**policy_options)
    hold=0;achieved=False;completion_step=None
    def observer(*args):
        nonlocal hold,achieved,completion_step
        g=task.grade(env);hold=hold+1 if g['success'] else 0
        if hold>=50 and not achieved:achieved=True;completion_step=int(env.step_count)
        if env.step_count%5==0:
            ps=task.poses(env);hands=[]
            for arm in ('left','right'):
                p,q=env.arm(arm).ee_pose(env.state)
                hands.append([*map(float,p),*map(float,q),float(env.gripper(arm).width(env.state))])
            samples.append(dict(step=int(env.step_count),poses={k:v.tolist() for k,v in ps.items()},hands=hands,
                                body_q=env.state.body_q.numpy().tolist(),joint_q=env.state.joint_q.numpy().tolist()))
        if env.step_count%50==0:checks.append(dict(step=int(env.step_count),**g))
    env.add_step_observer(observer)
    error=''
    r=None
    try:r=rollout(env,policy,episode_id=0,max_steps=max_steps)
    except Exception:error=traceback.format_exc()
    if r and r.success:
        for _ in range(75):env.step()
    final=task.grade(env)
    graph_success=bool(policy._result is not None and policy._result.success)
    result=dict(success=bool(achieved and final['success'] and r and r.success and graph_success),rss_success=bool(r and r.success),graph_success=graph_success,seed=seed,variant=asdict(v),graph=str(graph),observation_mode=observation,
                steps=int(env.step_count),sim_time_s=float(env.step_count/env.pipeline.control_hz),
                completion_step=completion_step,control_hz=float(env.pipeline.control_hz),
                wall_s=time.perf_counter()-start,final=final,events=events,error=error,
                graph_trace=policy.trace,
                workflow_sha256=hashlib.sha256((Path(graph)/'workflow.json').read_bytes()).hexdigest(),
                checkpoint_results=[c.to_dict() for c in getattr(policy._result,'checkpoint_results',[])],
                source_sha256=source_hashes)
    from .model import xy,CELLS,BEAD_Z
    if mode=='pyramid':
        from .pyramid import get_plan,physical
        target_beads={n:physical(p['sites']).tolist() for n,p in get_plan(v.pyramid_plan)['placements'].items()}
    else:target_beads={n:np.c_[xy(c),np.full(len(c),BEAD_Z)].tolist() for n,c in CELLS.items()}
    result['target_beads_local']=target_beads
    from .audit import audit
    result['independent_audit']=audit(result,samples)
    result['diagnostic_success']=bool(result['success'] and result['independent_audit']['success'])
    result['diagnostic_preset']=bool(v.preset_pieces)
    result['diagnostic_subset']=graph_params.get('diagnostic_subset',[])
    if observation=='rgb':
        result['rgb_observation_count']=len(policy.visual.records)
        result['policy_tool_allowlist']=sorted(policy.connector.tool_registry.runtime_tools())
        result['evaluator_is_policy_input']=False
        if result['diagnostic_subset']:
            subset_result={**result,'target_beads_local':{n:target_beads[n] for n in result['diagnostic_subset']}}
            result['independent_subset_audit']=audit(subset_result,samples)
            result['single_piece_physical_diagnostic']=dict(
                success=bool(graph_success and result['independent_subset_audit']['success'] and all(final['bead_error_m'][n]<.004 and final['speed_mps'][n]<.015 for n in result['diagnostic_subset'])),
                bead_error_m={n:final['bead_error_m'][n] for n in result['diagnostic_subset']},
                scope='subset diagnostic, all twelve initially loose; not full task success')
    result['success']=bool(result['diagnostic_success'] and not v.preset_pieces)
    if result['diagnostic_subset']:result['success']=False
    (d/'result.json').write_text(json.dumps(result,indent=2,default=str))
    (d/'frames.json').write_text(json.dumps(samples))
    (d/'checks.json').write_text(json.dumps(checks))
    policy.close()
    print(json.dumps({k:result[k] for k in ['success','seed','steps','sim_time_s','wall_s','error']}),flush=True)
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--graph',required=True);ap.add_argument('--out',required=True)
    ap.add_argument('--seed',type=int,default=0);ap.add_argument('--nominal',action='store_true');ap.add_argument('--max-steps',type=int,default=15000)
    ap.add_argument('--mode',choices=['flat','pyramid','completion'],default='flat')
    ap.add_argument('--motion',choices=['osc','plan'],default='osc')
    ap.add_argument('--observation',choices=['oracle','rgb'],default='oracle')
    ap.add_argument('--scattered',action='store_true')
    args=ap.parse_args();run(**vars(args));os._exit(0)
