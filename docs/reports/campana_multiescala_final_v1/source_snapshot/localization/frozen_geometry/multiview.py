"""RGB-only marker-local estimation. No simulator poses, identities or map input.

Optional runtime dependencies are the existing application's NumPy and OpenCV.
All thresholds are initial engineering heuristics, not calibrated accuracy claims.
"""
import math
import cv2
import numpy as np


def iou(a, b):
    a,b=np.asarray(a),np.asarray(b)
    wh=np.maximum(0,np.minimum(a[2:],b[2:])-np.maximum(a[:2],b[:2]))
    intersection=float(np.prod(wh))
    union=float(np.prod(a[2:]-a[:2])+np.prod(b[2:]-b[:2])-intersection)
    return intersection/union if union>0 else 0.


def marker_pose(corners, K, side=.1, max_error=3., ambiguity_gap=.25):
    """IPPE square, x right / y up / z outward; returns marker->optical camera."""
    h=side/2
    obj=np.array([[-h,h,0],[h,h,0],[h,-h,0],[-h,-h,0]],float)
    corners=np.asarray(corners,float).reshape(4,2)
    ok,rv,tv,_=cv2.solvePnPGeneric(obj,corners,np.asarray(K,float),None,flags=cv2.SOLVEPNP_IPPE_SQUARE)
    candidates=[]
    if ok:
        for r,t in zip(rv,tv):
            R=cv2.Rodrigues(r)[0]; t=t.reshape(3)
            if ((R@obj.T).T+t)[:,2].min()<=0:continue
            projected=cv2.projectPoints(obj,r,t,np.asarray(K,float),None)[0].reshape(-1,2)
            error=float(np.sqrt(np.mean(np.sum((projected-corners)**2,axis=1))))
            candidates.append({'R':R.tolist(),'t':t.tolist(),'reprojection_rmse_px':error})
    candidates.sort(key=lambda p:p['reprojection_rmse_px'])
    if not candidates:return {'status':'unavailable','reason':'no_positive_depth_pose'}
    if candidates[0]['reprojection_rmse_px']>max_error:
        return {'status':'unavailable','reason':'marker_reprojection','candidates':candidates}
    if len(candidates)>1 and candidates[1]['reprojection_rmse_px']-candidates[0]['reprojection_rmse_px']<ambiguity_gap:
        # Numerically identical solutions at exact frontal incidence are not distinct poses.
        if np.linalg.norm(np.asarray(candidates[0]['R'])-candidates[1]['R'])>1e-4:
            return {'status':'unavailable','reason':'ambiguous_marker_pose','candidates':candidates}
    return {'status':'estimated',**candidates[0],'candidates':candidates}


def triangulate(observations, K, min_parallax=3., max_reprojection=3.):
    """DLT in one repeatedly observed marker frame; fail closed on weak geometry."""
    if len(observations)<3:return {'status':'unavailable','reason':'fewer_than_three_observations'}
    marker_ids={o['marker_id'] for o in observations}
    if len(marker_ids)!=1:raise ValueError('Cannot merge different marker frames')
    K=np.asarray(K,float); rows=[]; centers=[]; rays=[]
    for o in observations:
        R=np.asarray(o['R']); t=np.asarray(o['t']); P=K@np.column_stack((R,t))
        x,y=o['point_px']; rows.extend([x*P[2]-P[0],y*P[2]-P[1]])
        centers.append(-R.T@t)
        ray=R.T@np.linalg.solve(K,[x,y,1]); rays.append(ray/np.linalg.norm(ray))
    angles=[math.degrees(math.acos(np.clip(np.dot(a,b),-1,1))) for i,a in enumerate(rays) for b in rays[i+1:]]
    parallax=max(angles)
    if parallax<min_parallax:return {'status':'unavailable','reason':'insufficient_parallax','parallax_deg':parallax}
    _,_,vt=np.linalg.svd(np.asarray(rows)); point=vt[-1]
    if abs(point[3])<1e-10:return {'status':'unavailable','reason':'point_at_infinity'}
    point=point[:3]/point[3]; errors=[]
    for o in observations:
        camera=np.asarray(o['R'])@point+o['t']
        if camera[2]<=0:return {'status':'unavailable','reason':'negative_depth'}
        pixel=K@camera; errors.append(float(np.linalg.norm(pixel[:2]/pixel[2]-o['point_px'])))
    if max(errors)>max_reprojection:
        return {'status':'unavailable','reason':'triangulation_reprojection','errors_px':errors,'parallax_deg':parallax}
    return {'status':'estimated','position_marker_m':point.tolist(),'parallax_deg':parallax,
            'reprojection_max_px':max(errors),'observations':len(observations)}


def unambiguous_assignment(scores, threshold=.2, gap=.15):
    """Reject ambiguous rows and competing predecessors, without arbitrary tie breaks."""
    scores=np.asarray(scores,float); proposed={}; rejected={}
    for i,row in enumerate(scores):
        candidates=np.flatnonzero(row>=threshold)
        if not len(candidates):rejected[i]='no_box_match';continue
        order=candidates[np.argsort(row[candidates])[::-1]]
        if len(order)>1 and row[order[0]]-row[order[1]]<gap:
            rejected[i]='ambiguous_box_match';continue
        proposed[i]=int(order[0])
    for j in set(proposed.values()):
        incoming=[i for i,v in proposed.items() if v==j]
        if len(incoming)>1:
            for i in incoming:del proposed[i]; rejected[i]='competing_tracks'
    return proposed,rejected


class Tracker:
    """Consecutive-frame LK flow and one-to-one boxes, with explicit rejected links."""
    def __init__(self):
        self.previous=None; self.active=[]; self.next_id=0; self.rejections=[]

    def update(self, image, detections, stamp_ns):
        gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY); assignments={}; rejected={}
        if self.previous is not None and self.active:
            scores=np.zeros((len(self.active),len(detections)))
            for i,old in enumerate(self.active):
                x1,y1,x2,y2=old['box']
                pts=np.array([[x1+(x2-x1)*u,y1+(y2-y1)*v] for u,v in
                              ((.3,.3),(.7,.3),(.5,.5),(.3,.7),(.7,.7))],np.float32).reshape(-1,1,2)
                nxt,ok,_=cv2.calcOpticalFlowPyrLK(self.previous,gray,pts,None)
                if nxt is None:rejected[i]='optical_flow_failed';continue
                back,ok2,_=cv2.calcOpticalFlowPyrLK(gray,self.previous,nxt,None)
                valid=(ok.ravel()!=0)&(ok2.ravel()!=0)&(np.linalg.norm(back-pts,axis=2).ravel()<=1.5)
                if valid.sum()<3:rejected[i]='optical_flow_unreliable';continue
                shift=np.median((nxt-pts)[valid,0],axis=0)
                shifted=np.array(old['box'])+np.tile(shift,2)
                scores[i]=[iou(shifted,d['box_xyxy_px']) for d in detections]
            matches,box_rejected=unambiguous_assignment(scores)
            rejected={**box_rejected,**rejected}
            assignments={j:self.active[i]['track_id'] for i,j in matches.items() if i not in rejected}
            self.rejections.extend({'stamp_ns':stamp_ns,'track_id':self.active[i]['track_id'],'reason':r}
                                   for i,r in rejected.items())
        self.active=[]
        for j,d in enumerate(detections):
            if j in assignments:identifier=assignments[j]
            else:identifier=f'track_{self.next_id:06d}'; self.next_id+=1
            d['track_id']=identifier
            self.active.append({'track_id':identifier,'box':d['box_xyxy_px']})
        self.previous=gray


def mask_boxes(labels):
    """Visible support only; an empty/occluded instance produces no reference box."""
    result=[]
    for identifier in np.unique(labels):
        if identifier==0:continue
        y,x=np.where(labels==identifier)
        result.append({'instance':int(identifier),'pixels':len(x),
                       'box':[int(x.min()),int(y.min()),int(x.max()+1),int(y.max()+1)]})
    return result


def match_detections(detections, references, threshold=.5):
    """Deterministic maximum-cardinality one-to-one IoU matching, not greedy counts."""
    edges={i:sorted((j for j,r in enumerate(references) if iou(d,r)>=threshold),
                    key=lambda j:-iou(d,references[j])) for i,d in enumerate(detections)}
    owner={}
    def augment(i,seen):
        for j in edges[i]:
            if j in seen:continue
            seen.add(j)
            if j not in owner or augment(owner[j],seen):owner[j]=i;return True
        return False
    for i in range(len(detections)):augment(i,set())
    matches={i:j for j,i in owner.items()}
    duplicates=[i for i in range(len(detections)) if i not in matches and edges[i]]
    return matches,duplicates
