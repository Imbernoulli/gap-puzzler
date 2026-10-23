"""Reuse the prior session's pinned RSS snapshot and sandbox lifecycle code."""
import os
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fleet.pool import Pool,Job,make_bundle,BUNDLE_EXCLUDE_PATHS
BUNDLE_EXCLUDE_PATHS.update({'live/run','results','site','dist'})

class PuzzlerPool(Pool):
    def bundle(self,refresh=False):
        if refresh or self._bundle is None:self._bundle=make_bundle(ROOT)
        return self._bundle

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--graph',required=True);ap.add_argument('--seeds',required=True)
    ap.add_argument('--out',required=True);ap.add_argument('--workers',type=int,default=2);ap.add_argument('--nominal',action='store_true')
    ap.add_argument('--mode',default='flat',choices=['flat','pyramid','completion'])
    a=ap.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    graph=Path(a.graph).resolve().relative_to(ROOT).as_posix()
    pool=PuzzlerPool('puzzler-'+time.strftime('%H%M%S'),cpu=8,memory=16,disk=30,
                     snapshot=os.environ.get('PUZZLER_DAYTONA_SNAPSHOT','gap-knot-rss-abed33ba-c8m16d30'),create_parallel=1,poll_s=4)
    jobs=[Job(id=f'iq-s{s}',cmd=f'python -u -m puzzler.episode --graph {graph} --mode {a.mode} --max-steps 30000 --seed {s} --out out/seed{s}'+(' --nominal' if a.nominal else ''),
              outputs=[f'out/seed{s}'],timeout_s=900,env={'CUDA_VISIBLE_DEVICES':'','OPENBLAS_NUM_THREADS':'1'}) for s in map(int,a.seeds.split(','))]
    try:
        result=pool.run(jobs,size=a.workers,results_dir=out,keep=False)
        rows=[]
        for r in result:
            p=Path(r.outputs_dir or '')/'out'/f'seed{r.id[4:]}'/'result.json'
            if p.exists():
                row=json.loads(p.read_text());row['result_path']=str(p);rows.append(row)
        (out/'summary.json').write_text(json.dumps(rows,indent=2))
    finally:
        pool.down()
        (out/'cleanup.json').write_text(json.dumps(dict(pool=pool.name,remaining=[s.id for s in pool.sandboxes(started_only=False)]),indent=2))

if __name__=='__main__':main()
