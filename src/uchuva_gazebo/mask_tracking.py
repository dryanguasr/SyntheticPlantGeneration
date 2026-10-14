"""Conservative flow/mask/appearance tracking, without maturity class barriers."""
import cv2
import numpy as np
from .localization import appearance
from .multiview import unambiguous_assignment


class PackedTrackMask:
    """Lossless persistent mask: one bit per pixel instead of one byte."""
    def __init__(self,mask):
        self.shape=mask.shape;self.packed=np.packbits(mask.reshape(-1))
    def dense(self):
        return np.unpackbits(self.packed,count=int(np.prod(self.shape))).reshape(self.shape).view(bool)
    def astype(self,dtype):return self.dense().astype(dtype)
    def __and__(self,other):return self.dense()&other
    def __or__(self,other):return self.dense()|other
    def __array__(self,dtype=None,copy=None):
        result=self.dense()
        return result.astype(dtype) if dtype is not None else result


class MaskTracker:
    def __init__(self,max_gap_seconds=2.,overlap_backend=None,flow_backend=None):
        self.gray=None;self.tracks={};self.next_id=0;self.rejections=[];self.max_gap=max_gap_seconds
        self.overlap_backend=overlap_backend
        self.flow_backend=flow_backend

    def propagate(self,gray,active,use_cuda=True):
        groups=[];owners=[]
        for old in active:
            old['flow_reliable']=False
            if self.gray is None:continue
            binary=old['mask'].astype(np.uint8)*255
            if self.flow_backend is not None:
                # Four pixels cover derivative, corner and NMS neighbourhoods.
                # Restrict computation to this mask instead of scanning 720p
                # separately for every active trajectory.
                x,y,w,h=cv2.boundingRect(binary);height,width=self.gray.shape
                x0=max(0,x-4);y0=max(0,y-4);x1=min(width,x+w+4);y1=min(height,y+h+4)
                points=cv2.goodFeaturesToTrack(self.gray[y0:y1,x0:x1],maxCorners=12,qualityLevel=.01,minDistance=2,mask=binary[y0:y1,x0:x1]) if w and h else None
                if points is not None:points+=np.array([x0,y0],np.float32)
            else:points=cv2.goodFeaturesToTrack(self.gray,maxCorners=12,qualityLevel=.01,minDistance=2,mask=binary)
            if points is not None:groups.append(points);owners.append(old)
        if not groups:return
        if self.flow_backend is not None and use_cuda:
            all_points=np.concatenate(groups)
            nxt,valid=self.flow_backend(self.gray,gray,all_points);offset=0
            results=[]
            for points in groups:
                size=len(points);results.append((nxt[offset:offset+size],valid[offset:offset+size]));offset+=size
        else:
            results=[]
            for points in groups:
                nxt,ok,_=cv2.calcOpticalFlowPyrLK(self.gray,gray,points,None)
                if nxt is None:results.append((points,np.zeros(len(points),bool)));continue
                back,ok2,_=cv2.calcOpticalFlowPyrLK(gray,self.gray,nxt,None)
                valid=np.zeros(len(points),bool) if back is None else ok.ravel().astype(bool)&ok2.ravel().astype(bool)&(np.linalg.norm(back-points,axis=2).ravel()<1.5)
                results.append((nxt,valid))
        for old,points,(nxt,valid) in zip(owners,groups,results):
            if valid.sum()<3:continue
            shift=np.median((nxt-points)[valid,0],axis=0)
            old['mask']=PackedTrackMask(cv2.warpAffine(old['mask'].astype(np.uint8),np.array([[1,0,shift[0]],[0,1,shift[1]]],np.float32),(gray.shape[1],gray.shape[0]),flags=cv2.INTER_NEAREST).astype(bool))
            old['box']=old['box']+np.tile(shift,2);old['flow_reliable']=True

    def restore_observation(self,image,detections,stamp_ns,masks,use_cuda=False):
        """Replay only recent motion; preserve saved identities, no reassociation."""
        now=stamp_ns/1e9;gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
        active=[t for t in self.tracks.values() if now-t['seen']<=self.max_gap]
        self.propagate(gray,active,use_cuda=use_cuda)
        for d,mask in zip(detections,masks):
            identifier=d['track_id']
            self.next_id=max(self.next_id,int(identifier.split('_')[-1])+1)
            self.tracks[identifier]=dict(id=identifier,seen=now,mask=PackedTrackMask(mask),box=np.asarray(d['box_xyxy_px'],float),appearance=np.asarray(d['appearance']))
        self.tracks={k:v for k,v in self.tracks.items() if now-v['seen']<=self.max_gap};self.gray=gray

    def update(self,image,detections,stamp_ns,masks):
        now=stamp_ns/1e9;gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
        if len(masks)!=len(detections):raise ValueError('One predicted mask per detection required')
        active=[t for t in self.tracks.values() if now-t['seen']<=self.max_gap]
        descriptors=[appearance(image,d['box_xyxy_px']) for d in detections]
        self.propagate(gray,active)
        scores=np.zeros((len(active),len(detections)))
        # Axis rejection is a necessary condition for the same circular gate.
        # Retain the original scalar norm and score arithmetic for candidates.
        centers=np.asarray([d['center_px'] for d in detections],dtype=float).reshape(-1,2)
        candidates=[]
        for i,old in enumerate(active):
            center=(old['box'][:2]+old['box'][2:])/2
            scale=max(8.,np.linalg.norm(old['box'][2:]-old['box'][:2]))
            nearby=np.flatnonzero(np.all(np.abs(centers-center)<=1.5*scale,axis=1))
            for j in nearby:
                distance=np.linalg.norm(center-centers[j])
                if distance<=1.5*scale:candidates.append((i,int(j),distance,scale))
        overlaps=None
        if self.overlap_backend is not None:
            pairs=[(i,j) for i,j,_,_ in candidates]
            overlaps=self.overlap_backend([t['mask'] for t in active],masks,pairs)
        for i,j,distance,scale in candidates:
            old=active[i]
            if overlaps is None:
                intersection=np.count_nonzero(old['mask']&masks[j]);union=np.count_nonzero(old['mask']|masks[j])
                overlap=intersection/max(1,union)
            else:overlap=overlaps[i,j]
            similarity=float(old['appearance']@descriptors[j])
            scores[i,j]=.5*overlap+.3*similarity+.2*max(0,1-distance/(1.5*scale))
            # Weak flow plus absent silhouette support cannot establish identity.
            if not old['flow_reliable'] and overlap<.15:scores[i,j]=0
        matches,rejected=unambiguous_assignment(scores,threshold=.5,gap=.08)
        assigned={j:active[i]['id'] for i,j in matches.items()}
        self.rejections.extend(dict(stamp_ns=stamp_ns,track_id=active[i]['id'],reason=r) for i,r in rejected.items())
        for j,d in enumerate(detections):
            identifier=assigned.get(j)
            if identifier is None:identifier=f'track_{self.next_id:06d}';self.next_id+=1
            d.update(track_id=identifier,appearance=descriptors[j].tolist())
            self.tracks[identifier]=dict(id=identifier,seen=now,mask=PackedTrackMask(masks[j]),box=np.asarray(d['box_xyxy_px'],float),appearance=descriptors[j])
        self.tracks={k:v for k,v in self.tracks.items() if now-v['seen']<=self.max_gap};self.gray=gray
