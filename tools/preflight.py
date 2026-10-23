"""Read-only full-pose grasp feasibility against an RSS-built scene."""
import argparse,json
from pathlib import Path
from puzzler.task import build,Variant,staging
from puzzler.tools import register
from puzzler.controller import plan
from robosimstudio_policy_agent.robot_tools import RobotTools

class DirectBus:
    def call(self,fn):return fn()

class Registry:
    def __init__(self):self.functions={}
    def register_callable(self,name,fn,**kwargs):self.functions[name]=fn
    def tool(self,name,**kwargs):return self.functions[name](**kwargs)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--graph',required=True);ap.add_argument('--mode',default='pyramid');ap.add_argument('--out',required=True)
    ap.add_argument('--pieces',default='')
    a=ap.parse_args();p=json.loads((Path(a.graph)/'params.json').read_text())
    env=build(Variant(mode=a.mode,pyramid_plan=p.get('pyramid_plan','pyramid_upright_plan.json'),
                      embodiment=p.get('embodiment','yam_bimanual')));env.reset();env.run(65)
    bus=DirectBus();ctx=Registry();register(ctx,env,bus)
    ctx.functions['robot.grasp_frame']=RobotTools(env,bus).grasp_frame
    p=json.loads((Path(a.graph)/'params.json').read_text());results={}
    for name,(_,_,arm) in staging().items():
        if a.pieces and name not in a.pieces.split(','):continue
        try:
            chosen=plan(ctx,name,{**p,**p.get('pieces',{}).get(name,{})},arm)
            results[name]={k:(v.tolist() if hasattr(v,'tolist') else v) for k,v in chosen.items() if k in ['index','heading','target_R','grasp','lean']}
            results[name]['feasible']=True
        except Exception as exc:results[name]={'feasible':False,'error':str(exc)}
        print(name,results[name],flush=True)
    Path(a.out).write_text(json.dumps(results,indent=2))

if __name__=='__main__':main()
