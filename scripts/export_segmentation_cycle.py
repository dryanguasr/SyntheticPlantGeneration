"""Validate visible instance masks and export accepted images to YOLO-seg."""
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
from uchuva_lsystem.segmentation_cycles import VERSION, CLASSES, class_for_grade, mask_polygon, write, sha


def inspect_capture(path):
    data=json.loads(path.read_text()); folder=path.parent
    image=cv2.imread(str(folder/'rgb.png'))
    raw=cv2.imread(str(folder/Path(data['mask']['path']).name))[:,:,::-1].astype(np.uint32)
    codes=(raw[:,:,0]<<16)|(raw[:,:,1]<<8)|raw[:,:,2]
    h,w=codes.shape; lines=[]; instances=[]; problems=[]
    palette=data['mask']['palette']; known={0}
    for identifier, item in data['mask']['items'].items():
        if identifier=='0' or not item.get('visible_pixels'): continue
        identity=item.get('instance_id')
        if identity not in data['grades']: raise ValueError(f'Visible target lacks grade: {identity}')
        color=palette[identifier]; code=(color[0]<<16)|(color[1]<<8)|color[2];known.add(code)
        mask=codes==code
        if int(mask.sum())!=item['visible_pixels']:raise ValueError('Mask pixel count differs')
        polygon,iou=mask_polygon(mask)
        if iou<.98:problems.append({'instance_id':identity,'reason':'polygon_iou','iou':iou,'pixels':int(mask.sum())})
        cls=class_for_grade(data['grades'][identity])
        lines.append(str(cls)+' '+' '.join(f'{x:.9f}' for x in polygon.ravel()))
        ys,xs=np.nonzero(mask)
        instances.append(dict(instance_id=identity,class_id=cls,pixels=int(mask.sum()),polygon_iou=iou,
            color_code=int(code),bbox=[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)]))
    if set(np.unique(codes))-known:raise ValueError('Unknown foreground mask values')
    detector=cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100))
    corners,ids,_=detector.detectMarkers(image)
    decoded=[] if ids is None else ids.ravel().tolist()
    return dict(source=str(path),seed=data['seed'],view=data['view'],instances=instances,
        problems=problems,lines=lines,aruco_decoded=decoded,whole_plant_in_frame=data['whole_plant_in_frame'],
        image_size=[w,h],mask_sha256=sha(folder/Path(data['mask']['path']).name),rgb_sha256=sha(folder/'rgb.png'))


def main():
    p=argparse.ArgumentParser();p.add_argument('--captures',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--inspect-only',action='store_true')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    inventory=[];counts=Counter()
    for path in sorted(a.captures.rglob('capture.json')):
        row=inspect_capture(path);lines=row.pop('lines');inventory.append(row)
        if row['problems'] or not row['instances']:continue
        if not a.inspect_only:
            split='train' if row['seed']<420118 else 'val'
            name=f"{row['seed']}_{row['view']:02d}"
            image=a.output/'images'/split/(name+'.png');image.parent.mkdir(parents=True,exist_ok=True)
            try:os.link(path.parent/'rgb.png',image)
            except OSError:shutil.copy2(path.parent/'rgb.png',image)
            label=a.output/'labels'/split/(name+'.txt');label.parent.mkdir(parents=True,exist_ok=True)
            label.write_text('\n'.join(lines)+'\n')
        counts.update(CLASSES[i['class_id']] for i in row['instances'])
    write(a.output/'inspection.json',dict(script_version=VERSION,seed=420100,
        parameter_preset='bouquet_calyx_appearance_cycles_v1',images=inventory,class_counts=dict(counts),
        accepted=sum(not r['problems'] and bool(r['instances']) for r in inventory),
        rejected=sum(bool(r['problems']) or not r['instances'] for r in inventory),
        training_eligible=False,reason='mesh acceptance and split freeze required'))
    if not a.inspect_only:
        (a.output/'dataset.yaml').write_text('path: '+a.output.resolve().as_posix()+'\ntrain: images/train\nval: images/val\nnames:\n'+''.join(f'  {i}: {name}\n' for i,name in enumerate(CLASSES)))
    print(json.dumps({'images':len(inventory),'accepted':sum(not r['problems'] for r in inventory),'counts':dict(counts)}))


if __name__=='__main__':main()
