"""Current four-RGB pyramid recognition via unlabelled lattice exact cover.

No evaluator or physical-state channel is read. The complete public lattice
is a tested hypothesis, not twelve supplied measurements. Current visible
materials constrain an exhaustive rigid-CAD packing search; hidden sites
remain inferred and all competing packings remain explicit.
"""
from copy import deepcopy
import hashlib

import cv2
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from . import model, pyramid
from .vision import NECK_RADIUS

CONTRACT='current_joint_pyramid_RGB_exact_cover_v1'
LIMITS=dict(median_outline_m=.0018,rms_outline_m=.004,
            max_lattice_correction_m=.003,occlusion_uncertainty_m=.004,
            minimum_site_samples=5,material_purity=.8,
            maximum_solutions=32,maximum_search_visits=200000,
            minimum_stable_interval_s=1.,maximum_stable_lattice_drift_m=.0018)
CAMERA_NAMES={'top','front','rear','side'}


def _neck_envelope():
    # Every public CAD neck joins nearest neighbors at PITCH. Splitting its
    # finite capsule at the midpoint, each half lies inside the enlarged
    # endpoint sphere. This bounds all possible necks before identity is known.
    required=float(np.hypot(model.PITCH/2,NECK_RADIUS))
    inflated=max(model.RADIUS,required)+LIMITS['occlusion_uncertainty_m']
    if required>inflated:raise ValueError('Public neck is not contained in visibility envelope')
    return dict(public_neck_radius_m=NECK_RADIUS,public_neck_length_m=model.PITCH,
        required_endpoint_cover_radius_m=required,inflated_endpoint_radius_m=inflated,
        maximum_surface_displacement_allowance_m=LIMITS['occlusion_uncertainty_m'],
        all_possible_public_necks_conservatively_covered=True)


def _material_masks(rgb):
    """Original palette thresholds, retaining every disconnected component.

    Packed neighbors can hide the visible neck of a rigid part. The ordinary
    single-piece detector's largest-component filter would then erase a real
    exposed bead; joint scene interpretation must retain those pixels.
    """
    a=rgb.astype(np.float32)/255.;norm=np.linalg.norm(a,axis=2)
    chroma=a/np.maximum(norm[...,None],1.e-6);names=list(model.CELLS)
    palette=np.array([model.COLORS[n]for n in names]);palette/=np.linalg.norm(palette,axis=1,keepdims=True)
    scores=chroma@palette.T;labels=scores.argmax(axis=2)
    valid=(scores.max(axis=2)>.995)&((a.max(axis=2)-a.min(axis=2))>.10)&(norm>.12)
    return {n:((labels==i)&valid).astype(np.uint8)for i,n in enumerate(names)}


def _near(origin,rays,cloud,radius):
    delta=cloud-origin;along=rays@delta.T
    perpendicular=np.maximum(0.,np.sum(delta*delta,axis=1)[None,:]-along*along)
    near=along-np.sqrt(np.maximum(0.,radius*radius-perpendicular))
    return np.where((along>0)&(perpendicular<radius*radius)&(near>0),near,np.inf)


def _fit(packet,images,cameras):
    board=np.asarray(packet['poses']['board'],dtype=float)
    rb=Rotation.from_quat(board[3:]).as_matrix()
    local=pyramid.physical(pyramid.SITES)
    base=local@rb.T+board[:3]
    views={}
    for key,cam in cameras.items():
        uv=cam.project(base)
        depths=((base-cam.camera_to_world[:3,3])@cam.camera_to_world[:3,:3])[:,2]
        radii=cam.K[0,0]*model.RADIUS/depths
        lo=np.maximum(0,np.floor((uv-radii[:,None]).min(axis=0)-15).astype(int))
        hi=np.minimum([images[key].shape[1],images[key].shape[0]],
                      np.ceil((uv+radii[:,None]).max(axis=0)+15).astype(int))
        crop=images[key][lo[1]:hi[1],lo[0]:hi[0]]
        masks=_material_masks(crop)
        union=np.maximum.reduce(list(masks.values()))
        contours,_=cv2.findContours(union,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)
        points=np.concatenate([c[:,0]for c in contours if len(c)>=15])if contours else np.empty((0,2))
        if len(points)>400:points=points[::int(np.ceil(len(points)/400))]
        views[key]=dict(camera=cam,lo=lo,masks=masks,rays=cam.rays(points+lo))
    if any(len(v['rays'])<35 for v in views.values()):
        raise ValueError('A calibrated RGB view lacks a resolved pyramid outline')
    def residual(x):
        centers=(base-board[:3])@Rotation.from_rotvec(x[3:]).as_matrix().T+board[:3]+x[:3]
        values=[]
        for v in views.values():
            delta=centers-v['camera'].camera_to_world[:3,3]
            errors=np.linalg.norm(np.cross(v['rays'][:,None,:],delta[None,:,:]),axis=2)-model.RADIUS
            values.append(errors.min(axis=1))
        return np.concatenate(values)
    fitted=least_squares(residual,np.zeros(6),loss='soft_l1',f_scale=.0008,
        diff_step=1.e-4,max_nfev=40,bounds=([-.006]*3+[-.08]*3,[.006]*3+[.08]*3))
    delta=fitted.x
    cloud=(base-board[:3])@Rotation.from_rotvec(delta[3:]).as_matrix().T+board[:3]+delta[:3]
    e=residual(delta)
    fit=dict(delta_translation_rotation_vector=delta.tolist(),
        median_outline_residual_m=float(np.median(np.abs(e))),
        rms_outline_residual_m=float(np.sqrt(np.mean(e*e))),
        maximum_site_change_from_board_m=float(np.linalg.norm(cloud-base,axis=1).max()),
        identity_used=False,public_goal_piece_assignment_used=False)
    return cloud,views,fit


def _site_evidence(cloud,views):
    names=list(model.CELLS);rows=[];angles=np.arange(12)*np.pi/6
    for index,center in enumerate(cloud):
        counts={n:0 for n in names};total=0;unclassified=0;by_view={};unique_pixels=set()
        for key,v in views.items():
            cam=v['camera'];origin=cam.camera_to_world[:3,3]
            toward=(origin-center)/np.linalg.norm(origin-center)
            x=np.cross(toward,[0.,0.,1.])
            if np.linalg.norm(x)<1.e-8:x=np.cross(toward,[1.,0.,0.])
            x/=np.linalg.norm(x);y=np.cross(toward,x)
            probes=[center]
            for r in (.35,.65):
                probes.extend(center+model.RADIUS*r*(np.cos(a)*x+np.sin(a)*y)for a in angles)
            uv=cam.project(np.asarray(probes));rays=cam.rays(uv)
            exact=_near(origin,rays,cloud,model.RADIUS);own=exact[:,index]
            others=_near(origin,rays,cloud,_neck_envelope()['inflated_endpoint_radius_m'])
            others[:,index]=np.inf
            # Only robustly exposed sphere pixels are mandatory evidence.
            # Neighbors within the declared4mm envelope may hide the rest.
            robust=np.isfinite(own)&(own+LIMITS['occlusion_uncertainty_m']<others.min(axis=1))
            xy=np.rint(uv).astype(int)-v['lo']
            h,w=next(iter(v['masks'].values())).shape
            robust&=(xy[:,0]>=0)&(xy[:,0]<w)&(xy[:,1]>=0)&(xy[:,1]<h)
            votes={n:0 for n in names};missing=0
            for px,py in xy[robust]:
                identity=next((n for n,m in v['masks'].items()if m[py,px]),None)
                if identity is None:missing+=1
                else:votes[identity]+=1;unique_pixels.add((key,int(px+v['lo'][0]),int(py+v['lo'][1])))
            for n in names:counts[n]+=votes[n]
            total+=int(robust.sum());unclassified+=missing
            by_view[key]=dict(robust_visible_samples=int(robust.sum()),
                material_votes={n:c for n,c in votes.items()if c},unclassified=missing)
        classified=sum(counts.values());best=max(counts,key=counts.get)
        purity=counts[best]/total if total else None
        confident=bool(total>=LIMITS['minimum_site_samples'] and purity>=LIMITS['material_purity'])
        foreign=sum(c for n,c in counts.items()if n!=best)
        view_contradiction=any(r['robust_visible_samples']>=LIMITS['minimum_site_samples']
            and r['material_votes'].get(best,0)/r['robust_visible_samples']<LIMITS['material_purity']
            for r in by_view.values())
        rows.append(dict(site_index=index,lattice_site=list(pyramid.SITES[index]),
            robust_visible_samples=total,unique_classified_pixel_count=len(unique_pixels),
            unclassified_samples=unclassified,material_votes={n:c for n,c in counts.items()if c},
            label=best if confident else None,purity=purity,by_view=by_view,
            fully_occluded_under_uncertainty=total<LIMITS['minimum_site_samples'],
            missing_material_contradiction=bool(total>=LIMITS['minimum_site_samples']and classified/total<.5),
            conflicting_material_contradiction=bool(total>=LIMITS['minimum_site_samples']
                and (not confident or foreign or view_contradiction))))
    return rows


def _packings(evidence):
    known={r['site_index']:r['label']for r in evidence if r['label']is not None}
    options=pyramid.candidates()
    names=list(model.CELLS);by_cell=[[]for _ in pyramid.SITES];counts={n:0 for n in names}
    for option in options:
        ids=[pyramid.INDEX[s]for s in option['sites']]
        if any(i in known and known[i]!=option['name']for i in ids):continue
        entry=(option['name'],option['mask'],1<<names.index(option['name']))
        counts[option['name']]+=1
        for i in ids:by_cell[i].append(entry)
    solutions=[];visits=0;exhausted=False;full=(1<<55)-1
    def search(occupied,used,path):
        nonlocal visits,exhausted
        visits+=1
        if visits>LIMITS['maximum_search_visits']or len(solutions)>=LIMITS['maximum_solutions']:
            exhausted=True;return
        if occupied==full:
            solutions.append({n:mask for n,mask,bit in path});return
        best=None
        for i in range(55):
            if occupied>>i&1:continue
            valid=[e for e in by_cell[i]if not(e[1]&occupied or e[2]&used)]
            if not valid:return
            if best is None or len(valid)<len(best):best=valid
            if len(best)==1:break
        for entry in best:
            search(occupied|entry[1],used|entry[2],path+[entry])
            if exhausted:return
    search(0,0,[])
    return solutions,dict(known_current_material_sites=len(known),
        candidate_counts_after_current_material_constraints=counts,
        solutions_found=len(solutions),search_visits=visits,search_exhausted=exhausted)


def analyze_terminal_rgb(packet,images,cameras,plan='pyramid_robot6_plan.json'):
    """Return a scene witness/refusal. Never fill packet poses or receipts."""
    from .pyramid import get_plan
    result=dict(contract=CONTRACT,status='unknown',complete=False,limits=dict(LIMITS),
        timestamp=packet.get('timestamp'),frame_sha256={k:hashlib.sha256(v.tobytes()).hexdigest()for k,v in images.items()},
        input_channels=['actual_RGB','calibration','current_RGB_board','public_rigid_CAD'],
        measured_piece_poses_created=False,physical_success_claimed=False)
    if (packet.get('observation_source')not in ('rgb_shape_geometry','calibrated_rgb_only')
            or packet.get('is_current_rgb')is False or 'board'not in packet.get('poses',{})
            or set(images)!=CAMERA_NAMES or set(cameras)!=CAMERA_NAMES
            or not isinstance(packet.get('timestamp'),(float,int))
            or not np.isfinite(packet['timestamp'])or packet['timestamp']<0
            or result['frame_sha256']!=packet.get('frame_sha256')
            or any(im.ndim!=3 or im.shape[2]!=3 or im.dtype!=np.uint8 for im in images.values())):
        return {**result,'reason':'Four current calibrated RGB views and current board are required'}
    try:
        result['neck_occlusion_envelope']=_neck_envelope()
        cloud,views,fit=_fit(packet,images,cameras);evidence=_site_evidence(cloud,views)
        result.update(shared_lattice_RGB_fit=fit,site_evidence=evidence,
            fitted_lattice_centers_world_m=cloud.tolist(),board_pose_from_current_RGB=packet['poses']['board'])
        if (fit['median_outline_residual_m']>=LIMITS['median_outline_m']
                or fit['rms_outline_residual_m']>=LIMITS['rms_outline_m']
                or fit['maximum_site_change_from_board_m']>=LIMITS['max_lattice_correction_m']):
            return {**result,'reason':'Complete unlabelled pyramid lacks original-scale current outline agreement'}
        if any(r['missing_material_contradiction']for r in evidence):
            return {**result,'reason':'A robustly exposed pyramid site lacks current material pixels'}
        if any(r['conflicting_material_contradiction']for r in evidence):
            return {**result,'reason':'A robustly exposed site has ambiguous or contrary current material evidence'}
        solutions,ambiguity=_packings(evidence);result['ambiguity']=ambiguity
        if ambiguity['search_exhausted']or len(solutions)!=1:
            return {**result,'reason':'Current visible materials do not establish one complete rigid-CAD packing'}
        raw=get_plan(plan)['placements']
        expected={n:sum(1<<pyramid.INDEX[tuple(s)]for s in p['sites'])for n,p in raw.items()}
        result['piece_evidence']={n:dict(
            current_labeled_sites=[i for i in range(55)if solutions[0][n]>>i&1 and evidence[i]['label']==n],
            inferred_hidden_sites=[i for i in range(55)if solutions[0][n]>>i&1 and evidence[i]['fully_occluded_under_uncertainty']],
            solution_site_indices=[i for i in range(55)if solutions[0][n]>>i&1])for n in model.CELLS}
        if solutions[0]!=expected:
            return {**result,'reason':'Unique current RGB/CAD packing differs from public target assignment'}
        if any(not r['current_labeled_sites']for r in result['piece_evidence'].values()):
            return {**result,'reason':'A piece has no current visible material evidence'}
        return {**result,'status':'unique_current_RGB_target_packing','complete':True,
            'reason':'Identity-independent lattice fit plus current RGB material constraints uniquely determine the public target packing',
            'uncertainty_scope':'4mm robust-visibility occlusion envelope is explicit. Hidden sites are inferred by unique rigid-CAD exact cover, not individually measured; continuous pose precision and untested non-lattice alternatives remain separate.'}
    except (ValueError,KeyError,TypeError,FloatingPointError)as error:
        return {**result,'reason':'Current joint RGB inference refused: '+str(error)}


def verify_terminal_scene(ctx,state):
    """Capture two fresh RGB witnesses; require stable scene interpretation."""
    from .vision_controller import PlanningRefusal
    from .modular_controller import save_observation
    prior=float(state.get('observation',{}).get('timestamp',-1.))
    first=ctx.tool('vision.observe',hints={'__observer_mode__':'terminal_joint_rgb'})
    if not validate_witness(first.get('terminal_joint_rgb_witness'),first)or float(first['timestamp'])<prior:
        raise PlanningRefusal('First current joint RGB terminal witness refused: '+str(first.get('terminal_joint_rgb_witness',{}).get('reason','missing observer wire or stale epoch')))
    waited=ctx.tool('robot.wait_steps',steps=50)
    if float(waited.get('waited',-1))<50:raise PlanningRefusal('Terminal stable RGB interval did not execute')
    second=ctx.tool('vision.observe',hints={'__observer_mode__':'terminal_joint_rgb'})
    witness=second.get('terminal_joint_rgb_witness')
    if not validate_witness(witness,second):
        raise PlanningRefusal('Second current joint RGB terminal witness refused: '+str((witness or {}).get('reason','missing observer wire')))
    pair=stable_pair(first,second)
    if not pair['accepted']:raise PlanningRefusal('Terminal current RGB pair is not stable: '+pair['reason'])
    new=save_observation(deepcopy(state),first);new=save_observation(new,second)
    new['terminal_joint_rgb_witness']=deepcopy(witness)
    new['terminal_joint_rgb_observation']=deepcopy(second)
    new['terminal_joint_rgb_stable_pair']=deepcopy(pair)
    new['terminal_joint_rgb_observations']=[deepcopy(first),deepcopy(second)]
    return new,witness


def stable_pair(first,second):
    try:
        a=first['terminal_joint_rgb_witness'];b=second['terminal_joint_rgb_witness']
        interval=float(second['timestamp'])-float(first['timestamp'])
        drift=float(np.linalg.norm(np.asarray(a['fitted_lattice_centers_world_m'])-np.asarray(b['fitted_lattice_centers_world_m']),axis=1).max())
        passed=bool(validate_witness(a,first)and validate_witness(b,second)
            and interval>=LIMITS['minimum_stable_interval_s']
            and drift<LIMITS['maximum_stable_lattice_drift_m']
            and all(a['piece_evidence'][n]['solution_site_indices']==b['piece_evidence'][n]['solution_site_indices']for n in model.CELLS))
        return dict(accepted=passed,interval_s=interval,maximum_shared_lattice_drift_m=drift,
            first_timestamp=first['timestamp'],second_timestamp=second['timestamp'],
            first_frame_sha256=first['frame_sha256'],second_frame_sha256=second['frame_sha256'],
            reason='Two fresh independently interpreted RGB scenes agree within declared bounds'if passed else'Timestamps, independently verified packing, or shared geometry differ beyond bounds')
    except (KeyError,TypeError,ValueError):return dict(accepted=False,reason='Malformed RGB pair')


def validate_witness(witness,observed):
    try:
        if not(witness['contract']==CONTRACT and witness['limits']==LIMITS
            and witness['status']=='unique_current_RGB_target_packing'and witness['complete']is True
            and witness['timestamp']==observed['timestamp']
            and np.isfinite(witness['timestamp'])and witness['timestamp']>=0
            and witness['frame_sha256']==observed['frame_sha256']
            and set(witness['frame_sha256'])==CAMERA_NAMES
            and all(isinstance(h,str)and len(h)==64 and all(c in '0123456789abcdef'for c in h)for h in witness['frame_sha256'].values())
            and observed['observation_source']in ('rgb_shape_geometry','calibrated_rgb_only')
            and observed.get('is_current_rgb')is not False
            and witness['board_pose_from_current_RGB']==observed['poses']['board']
            and witness['measured_piece_poses_created']is False
            and witness['physical_success_claimed']is False
            and witness['neck_occlusion_envelope']==_neck_envelope()):return False
        fit=witness['shared_lattice_RGB_fit']
        for field,limit in [('median_outline_residual_m','median_outline_m'),('rms_outline_residual_m','rms_outline_m'),('maximum_site_change_from_board_m','max_lattice_correction_m')]:
            if not 0<=float(fit[field])<LIMITS[limit]:return False
        if fit['identity_used']is not False or fit['public_goal_piece_assignment_used']is not False:return False
        cloud=np.asarray(witness['fitted_lattice_centers_world_m'],dtype=float)
        if cloud.shape!=(55,3)or not np.isfinite(cloud).all():return False
        board=np.asarray(observed['poses']['board'],dtype=float);rb=Rotation.from_quat(board[3:]).as_matrix()
        delta=np.asarray(fit['delta_translation_rotation_vector'],dtype=float)
        base=pyramid.physical(pyramid.SITES)@rb.T+board[:3]
        expected_cloud=(base-board[:3])@Rotation.from_rotvec(delta[3:]).as_matrix().T+board[:3]+delta[:3]
        if not np.allclose(cloud,expected_cloud,atol=1.e-10,rtol=0):return False
        if abs(float(np.linalg.norm(cloud-base,axis=1).max())-fit['maximum_site_change_from_board_m'])>1.e-10:return False
        evidence=witness['site_evidence']
        if len(evidence)!=55:return False
        for i,row in enumerate(evidence):
            if row['site_index']!=i or row['lattice_site']!=list(pyramid.SITES[i])or set(row['by_view'])!=CAMERA_NAMES:return False
            votes={n:0 for n in model.CELLS};total=0;unclassified=0
            for view in row['by_view'].values():
                count=view['robust_visible_samples'];missing=view['unclassified']
                if type(count)is not int or not 0<=count<=25 or type(missing)is not int or not 0<=missing<=count:return False
                if any(n not in votes or type(c)is not int or c<=0 for n,c in view['material_votes'].items()):return False
                if missing+sum(view['material_votes'].values())!=count:return False
                for n,c in view['material_votes'].items():votes[n]+=c
                total+=count;unclassified+=missing
            if row['robust_visible_samples']!=total or row['unclassified_samples']!=unclassified or row['material_votes']!={n:c for n,c in votes.items()if c}:return False
            if not 0<=row['unique_classified_pixel_count']<=total-unclassified:return False
            best=max(votes,key=votes.get);purity=votes[best]/total if total else None
            if row['purity']!=purity:return False
            visible=total>=LIMITS['minimum_site_samples'];confident=visible and purity>=LIMITS['material_purity']
            if row['label']!=(best if confident else None)or row['fully_occluded_under_uncertainty']!=(not visible):return False
            missing=visible and (total-unclassified)/total<.5
            conflict=visible and (not confident or any(c for n,c in votes.items()if n!=best)or any(v['robust_visible_samples']>=LIMITS['minimum_site_samples']and v['material_votes'].get(best,0)/v['robust_visible_samples']<LIMITS['material_purity']for v in row['by_view'].values()))
            if row['missing_material_contradiction']!=bool(missing)or row['conflicting_material_contradiction']!=bool(conflict)or missing or conflict:return False
        solutions,ambiguity=_packings(evidence)
        if witness['ambiguity']!=ambiguity or ambiguity['search_exhausted']or len(solutions)!=1:return False
        expected={n:sum(1<<pyramid.INDEX[tuple(s)]for s in p['sites'])for n,p in pyramid.get_plan('pyramid_robot6_plan.json')['placements'].items()}
        if solutions[0]!=expected or set(witness['piece_evidence'])!=set(model.CELLS):return False
        for n,mask in solutions[0].items():
            piece=dict(current_labeled_sites=[i for i in range(55)if mask>>i&1 and evidence[i]['label']==n],
                inferred_hidden_sites=[i for i in range(55)if mask>>i&1 and evidence[i]['fully_occluded_under_uncertainty']],
                solution_site_indices=[i for i in range(55)if mask>>i&1])
            if witness['piece_evidence'][n]!=piece or not piece['current_labeled_sites']:return False
        return True
    except (KeyError,TypeError,ValueError,IndexError,OverflowError):return False
