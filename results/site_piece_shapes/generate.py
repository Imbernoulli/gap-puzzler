"""CPU-only orthographic icons from the public bead and connector CAD."""
from pathlib import Path
from itertools import combinations
import importlib.util
import json
import math
import xml.etree.ElementTree as ET
import numpy as np
from puzzler import model
from puzzler.vision import cad_necks, NECK_RADIUS

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'site/media/pieces'
ORDER=('azure','orange','yellow','teal','purple','cyan','mint','lime','maroon','navy','pink','red')
VIEWBOX=128
PITCH_PX=24.
SCALE=PITCH_PX/model.PITCH
RADIUS_PX=model.RADIUS*SCALE
NECK_WIDTH_PX=2*NECK_RADIUS*SCALE
STROKE=1.4

def canonical(points):
    choices=[]
    for turn in range(4):
        rotation=model.rotation(turn*math.pi/2)
        projected=(points@rotation.T)[:,:2]*np.array([1.,-1.])
        q=np.rint((projected-projected.min(axis=0))/model.PITCH).astype(int)
        signature=tuple(sorted((int(y),int(x))for x,y in q))
        span=q.max(axis=0)+1
        score=(int(span[0]<span[1]),signature)
        choices.append((score,turn,projected,q))
    _,turn,projected,q=min(choices,key=lambda x:x[0])
    center=(projected.min(axis=0)+projected.max(axis=0))/2
    pixels=(projected-center)*SCALE+VIEWBOX/2
    return turn,pixels,q

def rotation_signature(q):
    variants=[]
    for turn in range(4):
        p=q.copy()
        for _ in range(turn):p=np.c_[-p[:,1],p[:,0]]
        p-=p.min(axis=0)
        variants.append(tuple(sorted(map(tuple,p.tolist()))))
    return min(variants)

OUT.mkdir(parents=True,exist_ok=True)
manifest=dict(schema='puzzler.site.public_piece_shape_icons.v1',
    source_CAD=dict(bead_centers='puzzler.model.local_beads(name)',
                    bead_radius_m=float(model.RADIUS),pitch_m=float(model.PITCH),
                    connectors='puzzler.vision.cad_necks(name)',neck_radius_m=float(NECK_RADIUS),
                    geometry='Exact public sphere circles and cylindrical neck top projection; no invented silhouette'),
    order=list(ORDER),viewBox=[0,0,VIEWBOX,VIEWBOX],background='transparent',
    palette='Identical neutral gray for every piece; identity is geometry, never material color',
    projection=dict(type='orthographic_top',axes='public local x/y, SVG y inverted',
                    orientation='Only quarter turns, prefer landscape; canonical lexicographic tie break. No reflections.',
                    pixels_per_m=SCALE,common_bead_diameter_px=2*RADIUS_PX),
    CPU_only=True,Env_created=False,GPU_used=False,pieces={})
signatures={}
for number,name in enumerate(ORDER,1):
    points=model.local_beads(name)
    necks=cad_necks(name)
    turn,pixels,q=canonical(points)
    signature=rotation_signature(q)
    assert signature not in signatures,(name,signatures.get(signature))
    signatures[signature]=name
    # Bead interiors may touch, as in the CAD, but no bead is hidden behind
    # another. The intentional bead/neck intersections are drawn neck-first.
    distances=[float(np.linalg.norm(a-b))for a,b in combinations(pixels,2)]
    assert min(distances)>=2*RADIUS_PX-1.e-7
    low=pixels.min(axis=0)-RADIUS_PX-STROKE/2
    high=pixels.max(axis=0)+RADIUS_PX+STROKE/2
    assert (low>0).all()and(high<VIEWBOX).all()
    assert all(abs(np.linalg.norm(points[a]-points[b])-model.PITCH)<1.e-7 for a,b in necks)
    title=f'Piece {number:02d}: {len(points)} beads'
    desc=f'Public CAD shape with {len(points)} spherical beads and {len(necks)} connecting necks. Orthographic top view.'
    rows=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEWBOX} {VIEWBOX}" width="128" height="128" role="img" aria-labelledby="title-{name} desc-{name}">',
          f'  <title id="title-{name}">{title}</title>',f'  <desc id="desc-{name}">{desc}</desc>',
          '  <g fill="none" stroke="#424b55" stroke-linecap="round">']
    for a,b in necks:
        x,y=pixels[a];xx,yy=pixels[b]
        rows.append(f'    <line data-beads="{a} {b}" x1="{x:.6f}" y1="{y:.6f}" x2="{xx:.6f}" y2="{yy:.6f}" stroke-width="{NECK_WIDTH_PX:.6f}"/>')
    rows+=['  </g>','  <g fill="#b9c0c7" stroke="#303943" stroke-width="1.4">']
    for index,(x,y)in enumerate(pixels):
        rows.append(f'    <circle data-bead="{index}" cx="{x:.6f}" cy="{y:.6f}" r="{RADIUS_PX:.6f}"/>')
    rows+=['  </g>','</svg>','']
    file=OUT/f'{name}.svg';file.write_text('\n'.join(rows))
    xml=ET.parse(file).getroot();ns={'s':'http://www.w3.org/2000/svg'}
    assert len(xml.findall('.//s:circle',ns))==len(points)
    assert len(xml.findall('.//s:line',ns))==len(necks)
    manifest['pieces'][name]=dict(order=number,shapeSrc=f'media/pieces/{name}.svg',
        file=str(file.relative_to(ROOT)),bead_count=len(points),neck_count=len(necks),
        source_local_bead_centers_m=points.tolist(),source_neck_bead_pairs=[list(x)for x in necks],
        quarter_turns=turn,rotation_degrees=90*turn,projected_centers_svg=pixels.tolist(),
        projected_bounds_including_stroke=[*low.tolist(),*high.tolist()],
        normalized_projected_lattice_points=q.tolist(),
        no_bead_interior_overlap=True,no_crop=True)
manifest['validation']=dict(piece_count=len(manifest['pieces']),total_beads=sum(x['bead_count']for x in manifest['pieces'].values()),
    all_12_unique_up_to_rotation=len(signatures)==12,
    exact_bead_and_neck_counts=True,all_12_share_one_viewBox=True,
    no_inadvertent_projected_bead_overlap=True,no_crop=True,
    smallest_canvas_margin_px=min(min(x['projected_bounds_including_stroke'][:2]+[VIEWBOX-v for v in x['projected_bounds_including_stroke'][2:]])for x in manifest['pieces'].values()))
assert manifest['validation']['total_beads']==55
(ROOT/'results/site_piece_shapes/manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest['validation'],indent=2))
print('cairosvg_available',importlib.util.find_spec('cairosvg')is not None)
