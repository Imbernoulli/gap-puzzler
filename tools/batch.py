"""Independent local CPU processes; each owns its complete RSS model/runtime."""
import argparse,json,os,subprocess,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def batch(graph,seeds,out,workers=4,nominal=False,mode='flat'):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    def job(seed):
        d=out/f'seed{seed:04d}';log=out/f'seed{seed:04d}.log'
        cmd=[str(ROOT/'tools/rss.sh'),'-u','-m','puzzler.episode','--graph',str(graph),'--mode',mode,'--max-steps','30000','--seed',str(seed),'--out',str(d)]
        if nominal:cmd+=['--nominal']
        t=time.perf_counter()
        with log.open('w') as f:
            try:rc=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=900).returncode
            except subprocess.TimeoutExpired:rc=124
        if (d/'result.json').exists():r=json.loads((d/'result.json').read_text())
        else:r=dict(success=False,seed=seed,error=f'process exit={rc}, see {log}')
        r['result_path']=str(d/'result.json');r['process_wall_s']=time.perf_counter()-t
        print(json.dumps({k:r.get(k) for k in ['seed','success','sim_time_s','wall_s','error']}),flush=True)
        return r
    rows=[]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for future in as_completed([ex.submit(job,s) for s in seeds]):
            rows.append(future.result());(out/'summary.json').write_text(json.dumps(sorted(rows,key=lambda r:r['seed']),indent=2))
    return rows

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--graph',required=True);ap.add_argument('--seeds',required=True)
    ap.add_argument('--out',required=True);ap.add_argument('--workers',type=int,default=4);ap.add_argument('--nominal',action='store_true')
    ap.add_argument('--mode',choices=['flat','pyramid','completion'],default='flat')
    a=ap.parse_args();batch(a.graph,[int(s) for s in a.seeds.split(',')],a.out,a.workers,a.nominal,a.mode)
