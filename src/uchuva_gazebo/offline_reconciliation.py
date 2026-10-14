"""Bounded multiview fitting and joint-refit identity reconciliation, RGB only."""
import copy
import numpy as np
from .localization import robust_triangulate
from .multiview import triangulate

VERSION='offline-calyx-map/2.0'


def representative_views(observations,maximum=30,minimum_seconds=.2):
    unique={o['observation_id']:o for o in observations}
    separated=[]
    for item in sorted(unique.values(),key=lambda o:o['stamp_ns']):
        if not separated or item['stamp_ns']-separated[-1]['stamp_ns']>=minimum_seconds*1e9-1:
            separated.append(item)
    if len(separated)>maximum:
        separated=[separated[i] for i in np.unique(np.linspace(0,len(separated)-1,maximum).astype(int))]
    return separated


def residuals(point,observations,K):
    rotation=np.asarray([o['R'] for o in observations]);translation=np.asarray([o['t'] for o in observations])
    camera=rotation@np.asarray(point)+translation
    projected=camera@np.asarray(K).T
    with np.errstate(divide='ignore',invalid='ignore'):
        errors=np.linalg.norm(projected[:,:2]/projected[:,2,None]-np.asarray([o['point_px'] for o in observations]),axis=1)
    errors[camera[:,2]<=0]=np.inf
    return errors


def fit_sequence(observations,K,minimum=8,maximum=30):
    sample=representative_views(observations,maximum)
    if len(sample)<minimum:return dict(status='unavailable',reason='insufficient_temporally_separated_support',selected_views=len(sample))
    fit=robust_triangulate(sample,K)
    if fit['status']!='estimated':return fit
    inlier_ids=set(fit['inlier_observation_ids']);selected=[o for o in sample if o['observation_id'] in inlier_ids]
    if len(selected)<minimum:return dict(status='unavailable',reason='insufficient_geometric_support',selected_views=len(selected))
    uncertainty=fit.get('uncertainty_m')
    if uncertainty is None or uncertainty>.03:return dict(status='unavailable',reason='unstable_triangulation',uncertainty_m=uncertainty)
    errors=residuals(fit['position_marker_m'],observations,K);valid=errors<=3
    if np.mean(valid)<.7:return dict(status='unavailable',reason='inconsistent_remaining_views',consistent_fraction=float(np.mean(valid)))
    fit.update(observations=int(valid.sum()),selected_views=len(selected),
        inlier_observation_ids=[o['observation_id'] for o,ok in zip(observations,valid) if ok],
        rejected_observation_ids=[o['observation_id'] for o,ok in zip(observations,valid) if not ok],
        remaining_views_consistency=float(np.mean(valid)),fit_method='bounded robust DLT; all remaining views checked',
        reprojection_p95_px=float(np.percentile(errors[valid],95)))
    return fit


def reconcile_offline(candidates,K,distance_m=.035):
    """Merge only non-coexisting identities, and rerun geometry after every merge.

    Ambiguous alternatives remain provisional. Full observation support is kept
    internally for refitting; callers can serialize it separately for efficiency.
    """
    maps=[];decisions=[]
    for original in sorted(candidates,key=lambda c:-len(c['source_observations'])):
        candidate=copy.deepcopy(original);matches=[]
        for index,old in enumerate(maps):
            if old['marker_id']!=candidate['marker_id']:continue
            if set(old['all_stamps'])&set(candidate['all_stamps']):continue
            if np.dot(old['appearance'],candidate['appearance'])<.85:continue
            if np.linalg.norm(np.asarray(old['position_marker_m'])-candidate['position_marker_m'])>distance_m:continue
            joint=old['source_observations']+candidate['source_observations']
            fit=fit_sequence(joint,K)
            if fit['status']=='estimated':matches.append((index,fit,joint))
            else:decisions.append(dict(track_ids=candidate['track_ids']+old['track_ids'],action='reject_merge',reason=fit['reason']))
        if len(matches)==1:
            index,fit,joint=matches[0];old=maps[index]
            old.update(fit);old['source_observations']=joint
            old['track_ids']+=candidate['track_ids'];old['all_stamps']+=candidate['all_stamps']
            old['observation_ids']=fit['inlier_observation_ids']
            old['state']='confirmed'
            decisions.append(dict(track_ids=old['track_ids'][:],action='merge_joint_geometry_refit'))
        else:
            candidate['map_id']=f'calyx_{len(maps):06d}'
            candidate['state']='provisional' if matches else candidate.get('state','confirmed')
            if matches:
                candidate['rejection_reasons']=['ambiguous_offline_identity']
                for index,_,_ in matches:
                    maps[index]['state']='provisional';maps[index]['rejection_reasons']=['ambiguous_offline_identity']
            maps.append(candidate)
    return maps,decisions
