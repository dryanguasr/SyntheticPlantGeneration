"""Budgeted visual diversity proposals; scale coverage still needs human review."""
import argparse
from collections import defaultdict
from pathlib import Path
import sys
import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from uchuva_dataset_curation import read_rows, write_json


def allocate(sizes, budget):
    """Proportional capacity allocation with at least one image per source."""
    if not len(sizes)<=budget<=sum(sizes.values()):
        raise ValueError('Budget cannot preserve all sources')
    allocation={key:1 for key in sizes}
    total=sum(sizes.values())
    for _ in range(budget-len(sizes)):
        key=max((k for k in sizes if allocation[k]<sizes[k]),
                key=lambda k:(sizes[k]*budget/total-allocation[k],k))
        allocation[key]+=1
    return allocation


def diverse_indices(features, count):
    # Compare against the nearest already retained image, never chains of reserves.
    start=len(features)//2
    selected=[start]
    distance=np.full(len(features),np.inf)
    for _ in range(count-1):
        distance=np.minimum(distance,np.mean((features-features[selected[-1]])**2,axis=1))
        distance[selected]=-1
        selected.append(int(np.argmax(distance)))
    return sorted(selected)


def describe(parent, row, relative_time):
    im=cv2.imread(str(parent/'thumbnails'/f"{row['image_id']}.jpg"))
    if im is None:
        raise ValueError(row['image_id'])
    im=cv2.resize(im,(32,32),interpolation=cv2.INTER_AREA)
    lab=cv2.cvtColor(im,cv2.COLOR_BGR2LAB).astype(np.float32)/255
    gray=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY).astype(np.float32)/255
    edge=cv2.magnitude(cv2.Sobel(gray,cv2.CV_32F,1,0),cv2.Sobel(gray,cv2.CV_32F,0,1))
    edge=cv2.resize(edge,(16,16),interpolation=cv2.INTER_AREA)
    hist=cv2.calcHist([cv2.cvtColor(im,cv2.COLOR_BGR2HSV)],[0,1],None,[8,8],[0,180,0,256]).ravel()/1024
    # Blocks normalized by dimension, keeping layout, texture and colour contributions explicit.
    return np.concatenate([lab.ravel()/np.sqrt(lab.size),
                           .4*edge.ravel()/np.sqrt(edge.size),.4*np.sqrt(hist),
                           np.array([.15*relative_time])]).astype(np.float32)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--total',type=int,default=2400)
    args=parser.parse_args()
    cv2.setNumThreads(2)
    rows=[r for r in read_rows(args.parent/'manifest.jsonl') if r['selection']=='include']
    targets={'train':round(args.total*.70),'val':round(args.total*.15)}
    targets['test']=args.total-sum(targets.values())
    kept=[];sources=[]
    for split,target in targets.items():
        photos=[r for r in rows if r['split']==split and r['kind']=='photo']
        kept.extend(r['image_id'] for r in photos)
        videos=defaultdict(list)
        for r in rows:
            if r['split']==split and r['kind']=='video':videos[r['source_id']].append(r)
        quotas=allocate({k:len(v) for k,v in videos.items()},target-len(photos))
        for sid,seq in sorted(videos.items()):
            seq.sort(key=lambda r:(r['timestamp_seconds'],r['image_id']))
            lo,hi=seq[0]['timestamp_seconds'],seq[-1]['timestamp_seconds']
            vectors=np.stack([describe(args.parent,r,(r['timestamp_seconds']-lo)/max(hi-lo,1)) for r in seq])
            selected=diverse_indices(vectors,quotas[sid])
            kept.extend(seq[i]['image_id'] for i in selected)
            sources.append(dict(source_id=sid,source=seq[0]['source'],split=split,before=len(seq),after=len(selected)))
    assert len(set(kept))==args.total
    write_json(args.output,dict(parent=args.parent.name,total=args.total,targets=targets,
        method='deterministic farthest-point appearance diversity within source, proportional per-source budget; all photos retained',
        limitation='Visual descriptors do not certify small-calyx or biological-scale coverage.',
        retained=sorted(kept),sources=sources))
    print(args.total,targets,flush=True)


if __name__=='__main__':main()
