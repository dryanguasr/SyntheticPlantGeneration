"""Evaluator-only visible instance summaries; never imported by the RGB estimator."""
import numpy as np


def visible_boxes(labels):
    """One vectorized pass over foreground pixels; no full-image scan per identity."""
    labels=np.asarray(labels)
    flat=np.flatnonzero(labels)
    if not len(flat):return []
    ids=labels.ravel()[flat].astype(np.int64)
    if ids.min()<1 or ids.max()>65535:raise ValueError('Expected positive 16-bit instance labels')
    count=np.bincount(ids);size=len(count)
    x=flat%labels.shape[1];y=flat//labels.shape[1]
    x0=np.full(size,labels.shape[1]);y0=np.full(size,labels.shape[0])
    x1=np.zeros(size,int);y1=np.zeros(size,int)
    np.minimum.at(x0,ids,x);np.minimum.at(y0,ids,y)
    np.maximum.at(x1,ids,x);np.maximum.at(y1,ids,y)
    return [{'instance':int(i),'pixels':int(count[i]),
             'box':[int(x0[i]),int(y0[i]),int(x1[i]+1),int(y1[i]+1)]} for i in np.flatnonzero(count)]
