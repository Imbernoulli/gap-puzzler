"""RSS native renderer over recorded body poses; no re-simulation or edited motion."""
import argparse,json
from pathlib import Path
import numpy as np

def render(episode,out,stride=4):
    import robosimstudio as rss
    from puzzler.task import scene,Variant
    import imageio.v2 as iio
    from PIL import Image,ImageDraw
    ep=Path(episode);result=json.loads((ep/'result.json').read_text())
    sim=scene(Variant(**result['variant'])).build()
    cam=rss.CameraSpec(name='replay',width=960,height=600,fov_y=48,
                       eye=(.88,-.75,1.26),look_at=(.39,-.05,.81),up=(0,0,1))
    all_frames=json.loads((ep/'frames.json').read_text());frames=all_frames[::stride]
    if frames[-1]['step']!=all_frames[-1]['step']:frames.append(all_frames[-1])
    out=Path(out);out.parent.mkdir(exist_ok=True,parents=True)
    verdict=('PRESET DIAGNOSTIC '+('PASS' if result.get('diagnostic_success') else 'FAILURE')
             if result.get('diagnostic_preset') else 'SUCCESS' if result['success'] else 'FAILURE')
    with iio.get_writer(str(out),fps=12,codec='libx264',quality=7,
                        output_params=['-threads','1']) as writer:
        for i,f in enumerate(frames):
            sim.state.body_q.assign(np.asarray(f['body_q'],np.float32))
            sim.state.joint_q.assign(np.asarray(f['joint_q'],np.float32))
            im=Image.fromarray(sim.render(cam)['rgb']);draw=ImageDraw.Draw(im)
            draw.rectangle((0,0,960,35),fill=(15,20,30));draw.text((12,10),f"RSS / GaP | seed {result['seed']} | t={f['step']/result['control_hz']:.1f}s | {verdict}",fill='white')
            writer.append_data(np.asarray(im))
            if i==0:im.save(out.with_suffix('.png'))
        im.save(out.with_name(out.stem+'_final.png'))
    print(out)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('episode');ap.add_argument('out');ap.add_argument('--stride',type=int,default=4)
    a=ap.parse_args();render(a.episode,a.out,a.stride)
