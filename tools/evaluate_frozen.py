"""Evaluate a new frozen graph against an archived, unchanged task protocol."""
import os
import argparse,hashlib,io,json,tarfile,time
from pathlib import Path
from daytona_batch import PuzzlerPool,Job,ROOT


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--protocol',required=True)
    ap.add_argument('--graph',required=True);ap.add_argument('--out',required=True)
    ap.add_argument('--seeds',default='20,21,100,101');ap.add_argument('--workers',type=int,default=4)
    a=ap.parse_args();source=Path(a.protocol);out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True)
    graph=Path(a.graph).resolve();relative=graph.relative_to(ROOT).as_posix()
    buffer=io.BytesIO()
    with tarfile.open(source/'protocol_bundle.tar.gz','r:gz') as old,tarfile.open(fileobj=buffer,mode='w:gz') as new:
        for member in old:
            if member.name==relative or member.name.startswith(relative+'/'):continue
            new.addfile(member,old.extractfile(member) if member.isfile() else None)
        for p in sorted(graph.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:new.add(p,arcname=p.relative_to(ROOT).as_posix())
    bundle=buffer.getvalue();digest=hashlib.sha256(bundle).hexdigest()[:12]
    (out/'protocol_bundle.tar.gz').write_bytes(bundle)
    protocol=json.loads((source/'protocol.json').read_text());protocol.update(bundle=digest,graph=relative,parent_protocol=str(source))
    (out/'protocol.json').write_text(json.dumps(protocol,indent=2))
    pool=PuzzlerPool('puzzler-frozen-'+time.strftime('%H%M%S'),cpu=8,memory=16,disk=30,
                     snapshot=os.environ.get('PUZZLER_DAYTONA_SNAPSHOT','gap-knot-rss-abed33ba-c8m16d30'),create_parallel=1,poll_s=4)
    pool.bundle=lambda refresh=False:(bundle,digest)
    seeds=list(map(int,a.seeds.split(',')))
    jobs=[Job(id=f'seed{s}',cmd=f'python -u -m puzzler.episode --graph {relative} --mode flat --seed {s} --max-steps 30000 --out out/seed{s}',
              outputs=[f'out/seed{s}'],timeout_s=1200,env={'CUDA_VISIBLE_DEVICES':'','OPENBLAS_NUM_THREADS':'1'}) for s in seeds]
    try:
        results=pool.run(jobs,size=a.workers,results_dir=out,keep=False);rows=[]
        for r in results:
            p=Path(r.outputs_dir or '')/'out'/r.id/'result.json'
            if not p.exists():raise RuntimeError(f'Missing episode: {r.id}: {r.status}: {r.error}')
            row=json.loads(p.read_text());row['result_path']=str(p)
            for name,sha in protocol['sources'].items():
                if row['source_sha256'].get(name)!=sha:raise RuntimeError(f'Protocol mismatch: {r.id}: {name}')
            rows.append(row)
        (out/'summary.json').write_text(json.dumps(rows,indent=2))
        print(f'Saved {len(rows)} complete episode records under common protocol {digest}.',flush=True)
    finally:
        pool.down()
        (out/'cleanup.json').write_text(json.dumps(dict(pool=pool.name,remaining=[s.id for s in pool.sandboxes(started_only=False)]),indent=2))


if __name__=='__main__':main()
