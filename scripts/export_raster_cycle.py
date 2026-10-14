"""Preserve all visible fragments in canonical uint16 instance rasters for YOLO."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import sys
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import VERSION, CLASSES, write, sha, group_seeds
from export_segmentation_cycle import inspect_capture


def main():
    p=argparse.ArgumentParser();p.add_argument('--captures',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--technical',action='store_true')
    p.add_argument('--protocol-root',type=Path)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    if not a.technical and a.protocol_root is None:
        raise ValueError('Main dataset requires the frozen common dataset budget')
    rows=[];counts=Counter();gates=[];excluded_partial_scenes=set()
    for path in sorted(a.captures.rglob('capture.json')):
        if not a.technical and not (path.parent.parent/'complete.json').exists():
            excluded_partial_scenes.add(str(path.parent.parent))
            continue
        row=inspect_capture(path);polygons=row.pop('lines')
        if a.technical:
            split='train' if row['view']==0 else 'val'
        else:
            groups=group_seeds()
            matches=[name for name in ('train','val') if row['seed'] in groups[name]]
            if len(matches)!=1:
                raise ValueError('Seed is outside frozen synthetic training/validation groups')
            split=matches[0]
            if any(r['seed']==row['seed'] and r['view']==row['view'] for r in rows):
                raise ValueError('Duplicate seed/view in dataset')
        if not row['instances']:raise ValueError('No visible target instances')
        row['split']=split;name=f"{row['seed']}_{row['view']:02d}"
        raw=cv2.imread(str(path.parent/'mask_calyx_crisp_v2.png'))[:,:,::-1].astype(np.uint32)
        codes=(raw[:,:,0]<<16)|(raw[:,:,1]<<8)|raw[:,:,2]
        raster=np.zeros(codes.shape,np.uint16)
        for i,item in enumerate(row['instances'],1):
            item['mask_id']=i;raster[codes==item['color_code']]=i
            assert int((raster==i).sum())==item['pixels']
        row['image']=f'images/{split}/{name}.png';row['mask']=f'masks/{split}/{name}.png'
        for key in ('image','mask'):(a.output/row[key]).parent.mkdir(parents=True,exist_ok=True)
        try:os.link(path.parent/'rgb.png',a.output/row['image'])
        except OSError:shutil.copy2(path.parent/'rgb.png',a.output/row['image'])
        assert cv2.imwrite(str(a.output/row['mask']),raster)
        assert np.array_equal(cv2.imread(str(a.output/row['mask']),-1),raster)
        row['raster_sha256']=sha(a.output/row['mask']);row['raster_iou']=1.0
        # Compatibility labels are separate, never substituted for raster ground truth.
        if not row['problems']:
            label=a.output/'polygon_compatible'/split/(name+'.txt');label.parent.mkdir(parents=True,exist_ok=True)
            label.write_text('\n'.join(polygons)+'\n')
        audit=json.loads((path.parent.parent/'mesh_audit.json').read_text())
        gates.append(audit.get('acceptance')=='passed' and row['whole_plant_in_frame'])
        rows.append(row);counts.update(CLASSES[i['class_id']] for i in row['instances'])
    if not a.technical:
        budget=json.loads((a.protocol_root/'common_dataset_budget.json').read_text())
        expected=set(budget['train_seeds']+budget['validation_seeds'])
        seen=Counter(r['seed'] for r in rows)
        if set(seen)!=expected or any(n!=budget['views_per_scene'] for n in seen.values()) or len(rows)!=budget['images_per_cycle']:
            raise ValueError('Incomplete dataset: seed/view counts differ from the frozen common budget')
    write(a.output/'raster_manifest.json',dict(script_version=VERSION,seed=420100,
        parameter_preset='exact_visible_masks',images=rows,class_counts=dict(counts)))
    write(a.output/'dataset_contract.json',dict(script_version=VERSION,seed=420100,
        parameter_preset='exact_visible_masks',classes=CLASSES,mask_source='lossless_RGB_ID_to_uint16',
        training_eligible=bool(rows) and all(gates) and not a.technical,technical_only=a.technical,
        native_mask_roundtrip_iou=1,polygon_export='only_instances_in_fully_compatible_images',
        excluded_partial_scenes=sorted(excluded_partial_scenes),
        polygon_rejected_images=sum(bool(r['problems']) for r in rows),
        protocol_refinement='Train from exact rasters to preserve holes and disconnected components',
        morphology_gate='passed' if all(gates) else 'unresolved'))
    (a.output/'dataset.yaml').write_text('path: '+a.output.resolve().as_posix()+'\ntrain: images/train\nval: images/val\nnames:\n'+''.join(f'  {i}: {n}\n' for i,n in enumerate(CLASSES)))
    print(json.dumps({'images':len(rows),'counts':dict(counts),'mesh_gate':all(gates)}))


if __name__=='__main__':main()
