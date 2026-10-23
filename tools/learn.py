"""Failure-directed GaP graph search, with held-out evaluation and an audit ledger.

Edits only controller parameters and regenerated skill nodes. Success gates,
task geometry and held-out seeds are never changed by the search.
"""
import argparse,json,re,statistics,subprocess,sys
from pathlib import Path
from make_graph import make

ROOT=Path(__file__).resolve().parents[1]

def measure(rows):
    successes=[r for r in rows if r.get('success') and r.get('rss_success')]
    times=[r['sim_time_s'] for r in successes]
    wall_times=[r['wall_s'] for r in successes]
    total_sim=sum(r['sim_time_s'] for r in rows)
    total_wall=sum(r['wall_s'] for r in rows)
    seated=[sum(e<.004 for e in r.get('final',{}).get('bead_error_m',{}).values()) for r in rows]
    n=len(rows);k=len(successes);z=1.96
    center=(k/n+z*z/(2*n))/(1+z*z/n) if n else 0.
    half=z*((k/n*(1-k/n)/n+z*z/(4*n*n))**.5)/(1+z*z/n) if n else 0.
    return dict(trials=n,successes=k,success_rate=k/n if n else 0.,
                wilson_95=[max(0.,center-half),min(1.,center+half)],
                mean_seated_pieces=statistics.mean(seated) if seated else 0.,
                mean_success_sim_s=statistics.mean(times) if times else None,
                total_evaluated_sim_s=total_sim,
                completed_puzzles_per_sim_hour=3600*k/total_sim if total_sim else None,
                mean_success_wall_s=statistics.mean(wall_times) if wall_times else None,
                total_evaluated_serial_wall_s=total_wall,
                completed_puzzles_per_serial_wall_hour=3600*k/total_wall if total_wall else None)

def rank(metrics):
    return (metrics['success_rate'],metrics['mean_seated_pieces'],-(metrics['mean_success_sim_s'] or 1e9))

def diagnose(rows):
    failures=[]
    for row in rows:
        if row.get('success'):continue
        result=Path(row.get('result_path',''))
        root=result.parent/'trace/0000/node_data'
        for p in root.glob('*/output.json'):
            d=json.loads(p.read_text())
            if d.get('failure'):failures.append(dict(piece=d.get('piece'),kind=d['failure']))
        error=json.dumps(row.get('graph_trace',{}))+' '+row.get('error','')
        match=re.search(r"([a-z]+)_sg[.]act.*?(No feasible source/target grasp|Full-pose planning refused)",error)
        if match:failures.append(dict(piece=match[1],kind='unreachable_pose'))
        if not failures:failures.append(dict(piece=None,kind='final_gate_or_runtime'))
    return failures

def propose(params,failures,metrics,mode):
    p=json.loads(json.dumps(params));changes=[]
    if metrics['success_rate']==1.:
        p['motion_scale']=round(min(2.,p.get('motion_scale',1.)*1.2),3)
        changes.append('Increase joint trajectory speed after every training episode passed.')
    else:
        p.update(full_task=True,terminal_grasp=True,grasp_auto=True,obstacle_grasp=True)
        changes.append('Enumerate collision-clear terminal grasps and validate source, carry and release poses.')
        for f in failures:
            if not f['piece']:continue
            part=p.setdefault('pieces',{}).setdefault(f['piece'],{})
            if f['kind']=='grasp_miss':
                part['grasp_z']=.006;part['close_width']=0.
                changes.append(f"{f['piece']}: pinch above the fingertip floor with full closure.")
            elif f['kind']=='unreachable_pose':
                part['shape_symmetry']=True
                part['transport']=max(.04,p.get('transport',.10)-.02)
                changes.append(f"{f['piece']}: search shape-preserving wrist alternatives and lower carry height.")
            elif f['kind']=='placement_error':
                p['motion_scale']=max(.6,p.get('motion_scale',1.)*.8)
                part['release_height']=.003 if mode=='pyramid' else .028
                changes.append(f"{f['piece']}: slow the carry and use the task's geometric release clearance.")
    return p,changes

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--graph',required=True);ap.add_argument('--out',required=True)
    ap.add_argument('--mode',choices=['flat','pyramid'],default='flat');ap.add_argument('--seeds',default='10,11')
    ap.add_argument('--test-seeds',default='100,101');ap.add_argument('--rounds',type=int,default=2)
    ap.add_argument('--backend',choices=['local','daytona'],default='local');ap.add_argument('--workers',type=int,default=2)
    a=ap.parse_args();train=[int(s) for s in a.seeds.split(',')];test=[int(s) for s in a.test_seeds.split(',')]
    if set(train)&set(test):raise ValueError('Training and test seeds must be disjoint.')
    out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True)
    graph=Path(a.graph).resolve();params=json.loads((graph/'params.json').read_text())
    workflow=json.loads((graph/'workflow.json').read_text());order=[k for k in workflow['subgraphs'] if k not in ('anchor_sg','finish_sg')]
    order=[n.removesuffix('_sg') for n in order]
    def evaluate(candidate,seeds,label):
        dest=out/label
        cmd=[sys.executable,str(ROOT/'tools'/('daytona_batch.py' if a.backend=='daytona' else 'batch.py')),
             '--graph',str(candidate),'--mode',a.mode,'--seeds',','.join(map(str,seeds)),
             '--workers',str(a.workers),'--out',str(dest)]
        with (out/(label+'.log')).open('w') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        rows=json.loads((dest/'summary.json').read_text())
        if len(rows)!=len(seeds):raise RuntimeError(f'{label}: expected {len(seeds)} recorded results, got {len(rows)}; inspect {dest}')
        return rows,measure(rows)
    ledger=[];rows,best=evaluate(graph,train,'train_00')
    ledger.append(dict(round=0,graph=str(graph),metrics=best,failures=diagnose(rows),accepted=True))
    for i in range(1,a.rounds+1):
        candidate_params,changes=propose(params,diagnose(rows),best,a.mode)
        candidate=ROOT/'graphs'/(out.name+f'_g{i:02d}')
        if candidate.exists():raise FileExistsError(candidate)
        make(candidate,candidate_params,retries=1,order=order)
        validator=ROOT/'third_party/robosimstudio/.venv/bin/gap'
        subprocess.run([str(validator),'run',str(candidate),'--validate-only'],cwd=ROOT,check=True,
                       env={**__import__('os').environ,'PYTHONPATH':str(ROOT)})
        trial_rows,metrics=evaluate(candidate,train,f'train_{i:02d}')
        accepted=rank(metrics)>rank(best)
        ledger.append(dict(round=i,graph=str(candidate),metrics=metrics,changes=changes,failures=diagnose(trial_rows),accepted=accepted))
        if accepted:graph,params,rows,best=candidate,candidate_params,trial_rows,metrics
        (out/'ledger.json').write_text(json.dumps(ledger,indent=2))
        print(json.dumps(ledger[-1]),flush=True)
    test_rows,test_metrics=evaluate(graph,test,'held_out')
    report=dict(mode=a.mode,training_seeds=train,test_seeds=test,selected_graph=str(graph),
                training_metrics=best,test_metrics=test_metrics,ledger=ledger,
                limitations=['Oracle pose perception in simulation.','Finite small-sample evaluation; not real-hardware evidence.'])
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
