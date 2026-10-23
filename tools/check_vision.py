"""Actual RSS RGB captures -> independent estimator -> evaluator-only metrics."""
import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import time

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.transform import Rotation

from puzzler import task, model
from puzzler.vision import estimate, detect
from puzzler.vision_observer import RGBSensor


def run(output, seeds=(201,202,203), scattered=True):
    d=Path(output);d.mkdir(parents=True,exist_ok=True)
    source_hashes={}
    for p in [model.ROOT/'puzzler/vision.py',model.ROOT/'puzzler/vision_observer.py',model.ROOT/'puzzler/task.py',Path(__file__)]:
        target=d/'source'/p.name;target.parent.mkdir(exist_ok=True);target.write_bytes(p.read_bytes())
        source_hashes[str(p.resolve().relative_to(model.ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    rows=[]
    for seed in seeds:
        v=replace(task.sample(seed),scattered=scattered)
        env=task.build(v)
        for _ in range(30):env.step()
        sensor=RGBSensor(env);images,timestamp=sensor.capture()
        # Estimator receives no env, seed, goal, true poses or variant metadata.
        start=time.perf_counter();observed=estimate(images,sensor.cameras);elapsed=time.perf_counter()-start
        truth=task.poses(env)  # Evaluation begins only after perception finished.
        errors={}
        for n in model.CELLS:
            if n not in observed['poses']:errors[n]=None;continue
            p=np.array(observed['poses'][n]);t=truth[n]
            a=model.local_beads(n)@Rotation.from_quat(p[3:]).as_matrix().T+p[:3]
            b=model.local_beads(n)@Rotation.from_quat(t[3:]).as_matrix().T+t[:3]
            cost=np.linalg.norm(a[:,None]-b[None,:],axis=2);ii,jj=linear_sum_assignment(cost)
            errors[n]=float(cost[ii,jj].max())
        np.savez_compressed(d/f'seed{seed}_rgb.npz',**images)
        overlay=images['top'].copy()
        for n,det in observed['detections'].items():
            if 'top' in det.get('boxes',{}):
                x0,y0,x1,y1=det['boxes']['top'];color=(80,255,200) if det['visible'] else (255,80,80)
                cv2.rectangle(overlay,(x0,y0),(x1,y1),color,2)
                cv2.putText(overlay,n,(x0,max(15,y0-5)),cv2.FONT_HERSHEY_SIMPLEX,.45,color,1)
        cv2.imwrite(str(d/f'seed{seed}_detection.jpg'),cv2.cvtColor(overlay,cv2.COLOR_RGB2BGR))
        row=dict(seed=seed,variant=asdict(v),timestamp=timestamp,estimator_wall_s=elapsed,source_sha256=source_hashes,
                 bead_error_m=errors,visible_count=sum(n in observed['poses'] for n in model.CELLS),
                 board_translation_error_m=float(np.linalg.norm(np.array(observed['poses']['board'])[:3]-truth['board'][:3])) if 'board' in observed['poses'] else None,
                 observation=observed,frame_sha256={k:hashlib.sha256(a.tobytes()).hexdigest() for k,a in images.items()})
        rows.append(row);print(seed,row['visible_count'],errors,flush=True)
        (d/'results.json').write_text(json.dumps(rows,indent=2))
        env.close()
    return rows


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',default='dist/vision-benchmark');p.add_argument('--seeds',default='201,202,203');p.add_argument('--staged',action='store_true')
    a=p.parse_args();run(a.out,tuple(map(int,a.seeds.split(','))),not a.staged)
