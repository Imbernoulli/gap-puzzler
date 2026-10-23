"""Explicit compound colliders: bead cavities and piece concavities stay open."""
import json
from pathlib import Path
import numpy as np
from .model import ROOT, CELLS, RADIUS, PITCH, local_beads

def generate():
    import trimesh as tm
    folder=ROOT/'assets';folder.mkdir(exist_ok=True)
    manifest={}
    def save(name,meshes):
        visual=folder/f'{name}.obj'
        tm.util.concatenate(meshes).export(visual)
        proxies=[]
        for i,m in enumerate(meshes):
            p=folder/f'{name}_{i:03d}.obj';m.export(p);proxies.append(str(p))
        manifest[name]=dict(path=str(visual),collision_path=proxies[0],collision_paths=proxies[1:])
    for name in CELLS:
        meshes=[]
        centers=local_beads(name)
        for p in centers:
            s=tm.creation.icosphere(subdivisions=2,radius=RADIUS);s.apply_translation(p);meshes.append(s)
        for i,a in enumerate(centers):
            for b in centers[i+1:]:
                delta=b-a
                if abs(np.linalg.norm(delta)-PITCH)>1e-7:continue
                neck=tm.creation.cylinder(radius=.0045,height=PITCH,sections=16)
                neck.apply_transform(tm.geometry.align_vectors([0,0,1],delta))
                neck.apply_translation((a+b)/2);meshes.append(neck)
        save(name,meshes)
    def box(ext,at):
        m=tm.creation.box(extents=ext);m.apply_translation(at);return m
    pieces=[box((.146,.296,.006),(0,0,0))]
    # A shallow socket lattice: bead centers are surrounded by four rounded posts.
    for i in range(6):
        for j in range(12):
            p=((i-2.5)*PITCH,(j-5.5)*PITCH,.007)
            s=tm.creation.cylinder(radius=.006,height=.008,sections=12);s.apply_translation(p);pieces.append(s)
    pieces += [box((.009,.315,.016),(a,0,.005)) for a in (-.078,.078)]
    pieces += [box((.165,.009,.016),(0,a,.005)) for a in (-.153,.153)]
    # The video's hinge and open lid border; no added grasping fixture.
    hinge=tm.creation.cylinder(radius=.013,height=.315,sections=24)
    hinge.apply_transform(tm.transformations.rotation_matrix(np.pi/2,[1,0,0]))
    hinge.apply_translation((.095,0,.014));pieces.append(hinge)
    pieces.append(box((.045,.315,.004),(.115,0,.003)))
    save('board',pieces)
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2))
    return manifest

def manifest():
    p=ROOT/'assets/manifest.json'
    if not p.exists():return generate()
    value=json.loads(p.read_text())
    if not all(Path(v['path']).exists() for v in value.values()):return generate()
    return value
