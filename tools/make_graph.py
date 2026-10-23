"""Generate small explicit GaP workflows, with separately routed retry nodes."""
import argparse,json
from pathlib import Path

def make(dest,params,retries=0,order=None):
    d=Path(dest);(d/'scripts').mkdir(parents=True,exist_ok=True)
    (d/'checkpoints').mkdir(exist_ok=True)
    nodes={};sg={};routes={}
    sequence=['anchor',*(order or ['navy','red','azure']),'finish']
    for i,name in enumerate(sequence):
        nodes[name]=dict(type='subgraph',ref=name+'_sg')
        fn='anchor(ctx,p)' if name=='anchor' else 'finish(ctx,p)' if name=='finish' else f'place(ctx,{name!r},p)'
        # Freeze the skill implementation in each graph so later edits cannot
        # retroactively change an evaluated candidate.
        skill=(Path(__file__).resolve().parents[1]/'puzzler/controller.py').read_text().replace('from . import model as m','from puzzler import model as m')
        (d/'scripts'/f'{name}.py').write_text(skill+'\n\ndef run(ctx):\n    p=params(__file__)\n    return '+fn+'\n')
        predicate = "g['finite'] and g['board_resting']" if name=='anchor' else "g['success']" if name=='finish' else f"g['bead_error_m'][{name!r}] < .004 and g['speed_mps'][{name!r}] < .015"
        (d/'checkpoints'/f'{name}_sg.py').write_text(
            'from gap.runtime.verify import Checkpoint\n\n'
            'def verified(world):\n    g=world.sim_state["puzzle_grade"]\n    return '+predicate+'\n\n'
            'def diagnostics(world):\n    return world.sim_state["puzzle_grade"]\n\n'
            f'CHECKPOINTS=[Checkpoint(name={name+"_physical_state"!r},subgraph={name+"_sg"!r},predicate=verified,validate=True,diagnostics_fn=diagnostics)]\n')
        outcomes=['ready'] if name=='anchor' else ['complete','failed'] if name=='finish' else ['placed','retry']
        sn=dict(act=dict(type='script',script=f'scripts/{name}.py'))
        sn.update({x:dict(type='noop') for x in outcomes})
        sg[name+'_sg']=dict(skill='generic',inputs={},outputs={},nodes=sn,
            edges=[['START','act']]+[[x,'END'] for x in outcomes],
            conditional_edges=dict(act=dict(router_field='route',mapping={x:x for x in outcomes})),
            exit=dict(router_field=None,success_values=outcomes),on_error='error')
        nxt=sequence[i+1] if i+1<len(sequence) else 'done'
        mapping={outcomes[0]:nxt,'error':'abort'}
        if len(outcomes)>1:mapping[outcomes[1]]='abort'
        routes[name]=dict(router_field='exit',mapping=mapping)
        if name not in ['anchor','finish']:
            for k in range(retries):
                prev=name if k==0 else name+f'_retry{k}'
                retry=name+f'_retry{k+1}'
                routes[prev]['mapping']['retry']=retry
                nodes[retry]=dict(type='subgraph',ref=name+'_sg')
                routes[retry]=dict(router_field='exit',mapping=dict(placed=nxt,retry='abort',error='abort'))
    nodes.update(done=dict(type='end',status='success'),abort=dict(type='end',status='failure'))
    g=dict(version=3,meta=dict(name=d.name,observation_mode='on_demand',description='Physically stabilize board; perceive, solve, grasp, insert, verify; release and retreat.'),
           nodes=nodes,edges=[['START','anchor']],conditional_edges=routes,subgraphs=sg)
    (d/'workflow.json').write_text(json.dumps(g,indent=2));(d/'params.json').write_text(json.dumps(params,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('dest');ap.add_argument('--params',default='{}');ap.add_argument('--retries',type=int,default=0)
    ap.add_argument('--order',default='')
    a=ap.parse_args();make(a.dest,json.loads(a.params),a.retries,a.order.split(',') if a.order else None)
