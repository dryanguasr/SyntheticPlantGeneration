"""RGB-only tracking, robust triangulation and marker-local reconciliation."""
import itertools
from collections import Counter
import cv2
import numpy as np
from .multiview import iou,triangulate,unambiguous_assignment

VERSION='calyx-marker-map/1.0'


def canonical_pose(pose,rig):
    rotation=np.asarray(pose['R'])
    return dict(R=(rotation@np.asarray(rig['R_marker_from_canonical'])).tolist(),
                t=(rotation@np.asarray(rig['t_marker_from_canonical_m'])+pose['t']).tolist())


def appearance(image,box):
    x,y,xx,yy=np.asarray(box,int);patch=image[max(0,y):yy,max(0,x):xx]
    if not patch.size:return np.zeros(16)
    hsv=cv2.cvtColor(patch,cv2.COLOR_BGR2HSV)
    hist=cv2.calcHist([hsv],[0],None,[16],[0,180]).ravel()
    return hist/max(float(np.linalg.norm(hist)),1.)


class PersistentTracker:
    """Single batched LK pass, bounded gaps and unambiguous appearance/box links."""
    def __init__(self):
        self.gray=None;self.tracks={};self.next_id=0;self.rejections=[]

    def update(self,image,detections,stamp_ns):
        now=stamp_ns/1e9;gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
        active=[v for v in self.tracks.values() if now-v['seen']<=2.]
        if self.gray is not None and active:
            points=np.array([[b['box'][0]+u*(b['box'][2]-b['box'][0]),b['box'][1]+v*(b['box'][3]-b['box'][1])] for b in active for u,v in [(0.3,0.3),(.7,.3),(.5,.5),(.3,.7),(.7,.7)]],np.float32).reshape(-1,1,2)
            nxt,ok,_=cv2.calcOpticalFlowPyrLK(self.gray,gray,points,None)
            if nxt is not None:
                back,ok2,_=cv2.calcOpticalFlowPyrLK(gray,self.gray,nxt,None)
                if back is not None:
                    valid=(ok.ravel()!=0)&(ok2.ravel()!=0)&(np.linalg.norm(back-points,axis=2).ravel()<1.5)
                    for i,track in enumerate(active):
                        valid_i=valid[i*5:(i+1)*5]
                        if valid_i.sum()>=3:
                            shift=np.median((nxt-points)[i*5:(i+1)*5,0][valid_i],axis=0)
                            track['box']=track['box']+np.tile(shift,2)
        self.gray=gray
        if detections is None:return
        descriptors=[appearance(image,d['box_xyxy_px']) for d in detections]
        scores=np.zeros((len(active),len(detections)))
        for i,track in enumerate(active):
            center=(track['box'][:2]+track['box'][2:])/2
            scale=max(10.,np.linalg.norm(track['box'][2:]-track['box'][:2]))
            for j,d in enumerate(detections):
                distance=np.linalg.norm(center-np.asarray(d['center_px']))
                if distance>2*scale:continue
                scores[i,j]=.45*iou(track['box'],d['box_xyxy_px'])+.3*float(track['appearance']@descriptors[j])+.25*max(0,1-distance/(2*scale))
        matches,rejected=unambiguous_assignment(scores,threshold=.48,gap=.08)
        assigned={j:active[i]['id'] for i,j in matches.items()}
        self.rejections.extend(dict(stamp_ns=stamp_ns,track_id=active[i]['id'],reason=r) for i,r in rejected.items())
        for j,d in enumerate(detections):
            identifier=assigned.get(j)
            if identifier is None:identifier=f'track_{self.next_id:06d}';self.next_id+=1
            self.tracks[identifier]=dict(id=identifier,seen=now,box=np.asarray(d['box_xyxy_px'],float),appearance=descriptors[j])
            d['track_id']=identifier;d['appearance']=descriptors[j].tolist()
        self.tracks={k:v for k,v in self.tracks.items() if now-v['seen']<=2.}


def robust_triangulate(observations,K):
    if len(observations)<3:return dict(status='unavailable',reason='fewer_than_three_observations')
    # Deterministic temporal spread; no truth or class used for geometric selection.
    indices=np.unique(np.linspace(0,len(observations)-1,min(12,len(observations))).astype(int))
    sample=[observations[i] for i in indices];best=[];best_error=float('inf')
    triples=list(itertools.combinations(range(len(sample)),3))
    hypothesis_outcomes=Counter()
    for position in np.unique(np.linspace(0,len(triples)-1,min(40,len(triples))).astype(int)):
        result=triangulate([sample[i] for i in triples[position]],K)
        hypothesis_outcomes[result.get('reason',result['status'])]+=1
        if result['status']!='estimated':continue
        point=np.asarray(result['position_marker_m']);inliers=[];errors=[]
        for o in observations:
            camera=np.asarray(o['R'])@point+o['t']
            if camera[2]<=0:continue
            pixel=np.asarray(K)@camera;error=np.linalg.norm(pixel[:2]/pixel[2]-o['point_px'])
            if error<=3:inliers.append(o);errors.append(error)
        mean=float(np.mean(errors)) if errors else float('inf')
        if len(inliers)>len(best) or (len(inliers)==len(best) and mean<best_error):best=inliers;best_error=mean
    if len(best)<3:return dict(status='unavailable',reason='no_consistent_three_view_geometry',
                              hypothesis_outcomes=dict(hypothesis_outcomes))
    result=triangulate(best,K)
    if result['status']=='estimated':
        deviations=[]
        for i in np.unique(np.linspace(0,len(best)-1,min(8,len(best))).astype(int)):
            fit=triangulate(best[:i]+best[i+1:],K)
            if fit['status']=='estimated':deviations.append(np.linalg.norm(np.asarray(fit['position_marker_m'])-result['position_marker_m']))
        result.update(inlier_observation_ids=[o['observation_id'] for o in best],rejected_observations=len(observations)-len(best),uncertainty_m=float(np.percentile(deviations,95)) if deviations else None,uncertainty_method='leave-one-out sensitivity; not calibrated confidence interval')
    return result


def reconcile(candidates,distance_m=.035):
    """Merge supported non-simultaneous tracks in the same calibrated marker frame."""
    maps=[]
    for candidate in sorted(candidates,key=lambda x:-x['observations']):
        matches=[]
        for index,existing in enumerate(maps):
            if candidate['marker_id']!=existing['marker_id']:continue
            if set(candidate['stamps'])&set(existing['stamps']):continue
            if np.dot(candidate['appearance'],existing['appearance'])<.85:continue
            if np.linalg.norm(np.asarray(candidate['position_marker_m'])-existing['position_marker_m'])<=distance_m:matches.append(index)
        if len(matches)==1:
            target=maps[matches[0]];target['track_ids']+=candidate['track_ids'];target['stamps']+=candidate['stamps'];target['observation_ids']+=candidate['observation_ids']
            target['observations']+=candidate['observations']
        else:
            candidate['map_id']=f'calyx_{len(maps):06d}'
            candidate['reconciliation_status']='ambiguous' if matches else 'separate'
            maps.append(candidate)
    return maps
