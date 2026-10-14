"""Evaluator-only panoptic decoding and confidence-ordered mask matching."""
import numpy as np
import math
from .flight_control import world_to_body


def whole_plant_in_frame(bounds,markers,position,quaternion,hfov_deg=60,resolution=(1280,720),margin=.05,hull_points=None):
    """Project full world-space mesh bounds and marker corners through body pose."""
    lower,upper=bounds
    points=(list(hull_points) if hull_points is not None else
            [[x,y,z] for x in (lower[0],upper[0]) for y in (lower[1],upper[1]) for z in (lower[2],upper[2])])
    for marker in markers:
        center=marker['center_world_m'];half=marker['side_m']/2
        points.extend([[center[0]+sx*half,center[1],center[2]+sz*half] for sx in (-1,1) for sz in (-1,1)])
    horizontal=math.tan(math.radians(hfov_deg)/2)
    vertical=horizontal*resolution[1]/resolution[0]
    for point in points:
        local=world_to_body([p-q for p,q in zip(point,position)],quaternion)
        forward,left,up=local[0]-.068,local[1],local[2]-.005
        if forward<=0:return False
        u=.5-left/(2*forward*horizontal);v=.5-up/(2*forward*vertical)
        if not (margin<=u<=1-margin and margin<=v<=1-margin):return False
    return True


def decode_panoptic_rgb(rgb,plant_count=36):
    """Gazebo: first two bytes are instance count; third is semantic label."""
    pixels=np.asarray(rgb)
    if pixels.ndim!=3 or pixels.shape[2]!=3 or pixels.dtype.kind not in 'ui':
        raise ValueError('Expected unsigned RGB labels, not colored visualization')
    if pixels.size and (pixels.min()<0 or pixels.max()>255):raise ValueError('Expected three byte channels')
    if not 1<=plant_count<=84:raise ValueError('Three class labels must fit one byte')
    pixels=pixels.astype(np.uint32)
    semantic=pixels[:,:,2]
    code=pixels[:,:,0]+256*pixels[:,:,1]+65536*semantic
    return np.where((semantic>=1)&(semantic<=plant_count*3),code,0)


def mask_matches(ious,predicted_classes,true_classes,thresholds,collapse=False):
    """Inputs must be ordered by descending prediction confidence."""
    ious=np.asarray(ious);predicted_classes=np.asarray(predicted_classes);true_classes=np.asarray(true_classes)
    if ious.shape!=(len(predicted_classes),len(true_classes)):raise ValueError('IoU shape differs from instances')
    matched=np.zeros((len(predicted_classes),len(thresholds)),bool);first={}
    for t,threshold in enumerate(thresholds):
        used=set()
        for i in range(len(predicted_classes)):
            options=[j for j in range(len(true_classes)) if j not in used and ious[i,j]>=threshold
                     and (collapse or predicted_classes[i]==true_classes[j])]
            if options:
                j=max(options,key=lambda j:ious[i,j]);used.add(j);matched[i,t]=True
                if t==0:first[i]=j
    return matched,first


def mask_confusion(ious,predicted_classes,true_classes,threshold=.5):
    """Rows truth, columns prediction; index 3 denotes background/unmatched."""
    _,matches=mask_matches(ious,predicted_classes,true_classes,[threshold],collapse=True)
    result=np.zeros((4,4),int)
    for i,j in matches.items():result[true_classes[j],predicted_classes[i]]+=1
    for i,cls in enumerate(predicted_classes):
        if i not in matches:result[3,cls]+=1
    for j,cls in enumerate(true_classes):
        if j not in matches.values():result[cls,3]+=1
    return result
