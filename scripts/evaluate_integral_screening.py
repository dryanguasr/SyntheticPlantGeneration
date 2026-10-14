"""Small evaluator-only comparison; never a final 3D winner selection."""
import json
from pathlib import Path
import sys
import time
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.continuous_evaluation import mask_iou_matrix,target_scope
from uchuva_gazebo.segmentation_evaluation import decode_panoptic_rgb,mask_matches
from uchuva_lsystem.segmentation_cycles import write


def read_selected_truth(path,stamps):
    """Stream our indented historical JSON, bounded by one frame, fail closed."""
    with path.open() as f:
        prefix=[]
        for line in f:
            if line.strip()=='"frames": [':break
            prefix.append(line)
        else:raise ValueError('Unknown truth layout')
        header=json.loads(''.join(prefix)+'"frames": []}')
        selected={};block=[]
        for line in f:
            if line.startswith('    {'):block=[line]
            elif block:
                block.append(line)
                if line.rstrip() in ('    },','    }'):
                    frame=json.loads(''.join(block).rstrip().rstrip(','));block=[]
                    if frame['stamp_ns'] in stamps:selected[frame['stamp_ns']]=frame
        if set(selected)!=stamps:raise ValueError('Missing selected ground truth')
    return header['objects'],selected


def main():
    root=ROOT/'outputs/integral_diagnosis_20261014';old=ROOT/'outputs/continuous_row_20261008'
    frames=json.loads((root/'public_screening/frames.json').read_text());stamps={r['stamp_ns'] for r in frames}
    objects,truth=read_selected_truth(old/'evaluator/truth.json',stamps)
    pairs={r['stamp_ns']:r for r in json.loads((old/'flight/full/paired/pairs.json').read_text())['pairs']}
    rows=[]
    for mode in ('full_960','full_1280','tiles_640','tiles_960'):
        cache=root/'perception'/mode;config=json.loads((cache/'configuration.json').read_text())
        counts=dict(target_observations=0,predictions=0,tp_class=0,tp_collapsed=0)
        latency=[];supports=set();start=time.perf_counter()
        for f in frames:
            stamp=f['stamp_ns'];record=json.loads((cache/f'{stamp}.json').read_text());props=record['proposals']
            with np.load(cache/f'{stamp}.npz') as pack:
                h,w=map(int,pack['shape']);masks=np.unpackbits(pack['packed_masks'],axis=1,count=h*w).reshape(-1,h,w).astype(bool)
            native=cv2.imread(str(old/'flight/full/paired'/pairs[stamp]['mask']))
            codes=decode_panoptic_rgb(native[:,:,::-1]);instances=truth[stamp]['instances']
            ious=mask_iou_matrix(masks,codes,instances);target,ignore=target_scope(ious,instances,objects)
            accepted=[i for i,p in enumerate(props) if p['accepted'] and not ignore[i]]
            pred=np.array([props[i]['class_id'] for i in accepted],int)
            gt=np.array([objects[str(instances[j]['code'])]['class_id'] for j in target],int)
            scoped=ious[np.ix_(accepted,target)]
            tp,_=mask_matches(scoped,pred,gt,np.array([.5]))
            collapsed,_=mask_matches(scoped,pred,gt,np.array([.5]),collapse=True)
            counts['tp_class']+=int(tp.sum());counts['tp_collapsed']+=int(collapsed.sum())
            counts['target_observations']+=len(target);counts['predictions']+=len(accepted)
            latency.append(record['seconds'])
        rows.append(dict(mode=mode,frames=len(frames),**counts,
            precision=counts['tp_class']/max(1,counts['predictions']),
            recall=counts['tp_class']/max(1,counts['target_observations']),
            collapsed_recall=counts['tp_collapsed']/max(1,counts['target_observations']),
            median_seconds=float(np.median(latency)),p95_seconds=float(np.percentile(latency,95)),
            evaluation_seconds=time.perf_counter()-start))
        write(root/'perception/screening_metrics.json',dict(version='perception-screening/1.0',rows=rows,
            scope='60 development frames; fixed historical threshold; not 3D selection or generalization',
            pending='full PR/AP and 3D comparison after screening'))
        print(mode,rows[-1],flush=True)


if __name__=='__main__':main()
