"""Build a frozen, explicitly RGB-driven GaP workflow, never oracle checkpoints."""
import argparse
import json
from pathlib import Path

from tools.make_graph import make


def build(dest, order=None, mode='flat'):
    root=Path(__file__).resolve().parents[1]
    params=json.loads((root/'graphs/flat_v10/params.json').read_text())
    params.update(mode=mode, pyramid_plan='pyramid_robot6_plan.json', safe_anchor=True, release_height=.012)
    if order and len(order)<12:params['diagnostic_subset']=order
    order=order or ['orange','purple','yellow','lime','teal','cyan','azure','navy','pink','maroon','mint','red']
    make(dest,params,retries=1,order=order)
    d=Path(dest)
    controller=(root/'puzzler/vision_controller.py').read_text().replace('from . import model as m','from puzzler import model as m')
    for path in (d/'scripts').glob('*.py'):
        name=path.stem
        fn='anchor(ctx,p)' if name=='anchor' else 'finish(ctx,p)' if name=='finish' else f'place(ctx,{name!r},p)'
        path.write_text(controller+'\n\ndef run(ctx):\n    p=params(__file__)\n    return '+fn+'\n')
    for path in (d/'checkpoints').glob('*.py'):
        name=path.stem.removesuffix('_sg')
        if name=='anchor':predicate="'board' in v.get('poses',{})"
        elif name=='finish':predicate='all(a["bead_error_m"].get(n) is not None and a["bead_error_m"][n]<.003 for n in '+repr(params.get('diagnostic_subset',list(__import__('puzzler.model',fromlist=['CELLS']).CELLS)))+')'
        else:predicate=f'a.get("bead_error_m",{{}}).get({name!r}) is not None and a["bead_error_m"][{name!r}]<.003'
        path.write_text('from gap.runtime.verify import Checkpoint\n\ndef verified(world):\n    v=world.sim_state.get("vision",{})\n    a=v.get("assessment",{})\n    return '+predicate+'\n\nCHECKPOINTS=[Checkpoint(name='+repr(name+'_visual_estimate')+',subgraph='+repr(name+'_sg')+',predicate=verified,validate=True)]\n')
    g=json.loads((d/'workflow.json').read_text())
    g['meta'].update(description='RGB-only detection, multi-view CAD fitting and motor control; visual checkpoints only.',
                     observation_contract='RGB + fixed calibration + robot encoders; no evaluator input')
    (d/'workflow.json').write_text(json.dumps(g,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('dest');ap.add_argument('--order');ap.add_argument('--mode',default='flat',choices=['flat','pyramid'])
    a=ap.parse_args();build(a.dest,a.order.split(',') if a.order else None,a.mode)
