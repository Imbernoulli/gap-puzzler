"""Paired evaluation under one archived code bundle; select using training seeds only."""
import os
import argparse,hashlib,json,time
from pathlib import Path
from daytona_batch import PuzzlerPool,Job,ROOT
from learn import measure,rank


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',required=True)
    ap.add_argument('--seeds',default='20,21')
    ap.add_argument('--test-seeds',default='100,101')
    ap.add_argument('--workers',type=int,default=4)
    a=ap.parse_args();out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True)
    train=list(map(int,a.seeds.split(',')));test=list(map(int,a.test_seeds.split(',')))
    if set(train)&set(test):raise ValueError('Train and held-out seeds overlap.')
    graphs={'fixed':'graphs/benchmark_fixed','adaptive':'graphs/benchmark_adaptive','fast':'graphs/benchmark_fast'}
    pool=PuzzlerPool('puzzler-compare-'+time.strftime('%H%M%S'),cpu=8,memory=16,disk=30,
                     snapshot=os.environ.get('PUZZLER_DAYTONA_SNAPSHOT','gap-knot-rss-abed33ba-c8m16d30'),create_parallel=1,poll_s=4)
    # Preserve precisely what every job imports, including the evaluator. This
    # prevents ongoing development elsewhere from confounding this comparison.
    bundle,digest=pool.bundle();(out/'protocol_bundle.tar.gz').write_bytes(bundle)
    protocol={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted((ROOT/'puzzler').glob('*.py'))}
    (out/'protocol.json').write_text(json.dumps(dict(bundle=digest,sources=protocol,train=train,test=test,graphs=graphs),indent=2))
    jobs=[]
    for label,graph in graphs.items():
        for split,seeds in [('train',train),('held_out',test if label!='fixed' else [])]:
            for seed in seeds:
                name=f'{label}-{split}-s{seed}'
                jobs.append(Job(id=name,cmd=f'python -u -m puzzler.episode --graph {graph} --mode flat --max-steps 30000 --seed {seed} --out out/{name}',
                                outputs=[f'out/{name}'],timeout_s=1200,env={'CUDA_VISIBLE_DEVICES':'','OPENBLAS_NUM_THREADS':'1'}))
    # Pool.run normally refreshes the bundle; bind the already archived bytes.
    pool.bundle=lambda refresh=False:(bundle,digest)
    try:
        results=pool.run(jobs,size=a.workers,results_dir=out,keep=False)
        rows={};infrastructure=[]
        for r in results:
            p=Path(r.outputs_dir or '')/'out'/r.id/'result.json'
            if not p.exists():infrastructure.append(dict(job=r.id,status=r.status,error=r.error));continue
            row=json.loads(p.read_text());row['result_path']=str(p);rows[r.id]=row
            for source,sha in protocol.items():
                if row['source_sha256'].get(source)!=sha:raise RuntimeError(f'Protocol mismatch: {r.id}: {source}')
        if infrastructure:raise RuntimeError(f'Missing recorded trials: {infrastructure}')
        metrics={label:measure([rows[f'{label}-train-s{s}'] for s in train]) for label in graphs}
        selected=max(metrics,key=lambda name:rank(metrics[name]))
        # The selection file is committed before held-out metrics are read.
        (out/'selection.json').write_text(json.dumps(dict(selected=selected,training=metrics),indent=2))
        held=measure([rows[f'{selected}-held_out-s{s}'] for s in test]) if selected!='fixed' else None
        base=metrics['adaptive']['mean_success_sim_s'];fast=metrics['fast']['mean_success_sim_s']
        report=dict(protocol_bundle=digest,training=metrics,selected=selected,selected_graph=graphs[selected],held_out=held,
                    speed_time_reduction_fraction=1-fast/base if base and fast else None,
                    strict_success='Native RSS goal, completed GaP graph and independent released-trajectory audit all pass.',
                    limitations=['Two training and two held-out seeds: wide confidence intervals.',
                                 'Oracle perception; simulation only.','Small-sample rates do not establish broad robustness.'])
        (out/'summary.json').write_text(json.dumps(rows,indent=2))
        (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
    finally:
        pool.down()
        (out/'cleanup.json').write_text(json.dumps(dict(pool=pool.name,remaining=[s.id for s in pool.sandboxes(started_only=False)]),indent=2))


if __name__=='__main__':main()
