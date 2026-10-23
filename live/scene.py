import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import robosimstudio as rss
import json
import importlib
import puzzler.model,puzzler.assets,puzzler.hardware,puzzler.task,puzzler.pyramid,puzzler.tools
for module in (puzzler.model,puzzler.assets,puzzler.hardware,puzzler.task,puzzler.pyramid,puzzler.tools):
    importlib.reload(module)
from puzzler.task import scene as make_scene,Variant
HERE=Path(__file__).resolve().parent
config=json.loads((HERE/'config.json').read_text()) if (HERE/'config.json').exists() else {}
variant=Variant(mode=config.get('mode','flat'),pyramid_plan=config.get('pyramid_plan','pyramid_upright_plan.json'),
                embodiment=config.get('embodiment','yam_bimanual'))
scene=make_scene(variant,completed=config.get('completed',False))
pyramid=variant.mode=='pyramid'
scene.add(rss.CameraSpec(name='phone',width=640,height=360,fov_y=42,
    eye=(.510,.036,1.12) if pyramid else (.458,-.014,1.03),
    look_at=(.510,.036,.75) if pyramid else (.458,-.014,.75),
    up=(.559,-.829,0) if pyramid else (.9945,-.1045,0)))
scene.add(rss.CameraSpec(name='workcell',width=960,height=540,fov_y=50,
    eye=(.94,-.66,1.35),look_at=(.42,0,.79),up=(0,0,1)))

def settle(sim):
    for _ in range(100):
        sim.step();yield
routines={'settle':settle}
if config.get('execute'):
    from puzzler.task import build
    from puzzler.tools import register
    from puzzler.policy import VerifiedGraph
    sim=build(variant,max_steps=30000)
    sim._cameras=tuple(scene.cameras)
    def assemble(sim,session):
        graph=str(HERE.parent/config.get('graph','graphs/flat_v5'))
        trace=HERE/'run'/config.get('trace','live_trace')
        policy=VerifiedGraph(sim,graph=graph,roll='held',task_tools=register,trace_dir=str(trace),bus_timeout=600.,settle_steps=150)
        obs,info=sim.reset();policy.reset(obs,info)
        for panel in session.arms.values():panel.suspend()
        try:
            for _ in range(30000):
                action=policy.get_action(obs)
                obs,reward,done,truncated,info=sim.step(action,mode=policy.control_mode)
                policy.on_step(obs,reward,info);yield
                if done or truncated:break
            from puzzler.task import grade
            result=dict(mode=variant.mode,graph=graph,steps=sim.step_count,
                        rss_success=bool(info.get('success')),graph_success=bool(policy._result and policy._result.success),
                        grade=grade(sim),checkpoints=[c.to_dict() for c in getattr(policy._result,'checkpoint_results',[])])
            trace.mkdir(parents=True,exist_ok=True)
            (trace/'live_result.json').write_text(json.dumps(result,indent=2))
        finally:
            policy.close()
            for panel in session.arms.values():panel.resume()
            session.set_paused(True)
    routines['assemble']=assemble
