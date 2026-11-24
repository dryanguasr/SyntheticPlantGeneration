"""Evaluator-only mask matching and target/background accounting."""
import numpy as np


def packed_mask_iou_matrix(packed, shape, codes, instances, batch_size=16):
    """Same mask IoUs, with bounded unpacked storage instead of all proposals."""
    if batch_size < 1:
        raise ValueError('Positive batch size required')
    h,w=map(int,shape)
    result=np.zeros((len(packed),len(instances)),float)
    for start in range(0,len(packed),batch_size):
        masks=np.unpackbits(packed[start:start+batch_size],axis=1,count=h*w).reshape(-1,h,w).view(np.bool_)
        result[start:start+len(masks)]=mask_iou_matrix(masks,codes,instances)
    return result


def mask_iou_matrix(masks,codes,instances):
    result=np.zeros((len(masks),len(instances)),float)
    areas=[int(mask.sum()) for mask in masks]
    for j,instance in enumerate(instances):
        x,y,xx,yy=instance['bbox'];truth=codes[y:yy,x:xx]==instance['code']
        for i,mask in enumerate(masks):
            intersection=np.count_nonzero(mask[y:yy,x:xx]&truth)
            result[i,j]=intersection/max(1,areas[i]+instance['pixels']-intersection)
    return result


def one_to_one_masks(ious,threshold=.5):
    """Maximum-cardinality bipartite matching with IoU-ranked augmentations."""
    edges={i:sorted(np.flatnonzero(row>=threshold),key=lambda j:-row[j]) for i,row in enumerate(ious)}
    owners={}
    def augment(i,seen):
        for j in edges[i]:
            if j in seen:continue
            seen.add(j)
            if j not in owners or augment(owners[j],seen):owners[j]=i;return True
        return False
    for i in range(len(ious)):augment(i,set())
    return {i:int(j) for j,i in owners.items()}


def target_scope(ious,instances,objects):
    target=[j for j,item in enumerate(instances) if objects[str(item['code'])]['role']=='target']
    context=[j for j in range(len(instances)) if j not in target]
    # Background proposals are outside this 2D measurement only. This function
    # must never filter estimator observations or the resulting 3D target map.
    ignore=[]
    for row in ious:
        background=max(row[context],default=0)
        foreground=max(row[target],default=0)
        ignore.append(background>=.5 and foreground<.5)
    return target,np.asarray(ignore,bool)
