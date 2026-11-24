"""Prepare an 80/20 image mixture using only existing synthetic training views."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil

import cv2
import numpy as np
from prepare_union_pilot import ROOT, SEED, sha, write


def main():
    out=ROOT/'mixed_dataset'
    if out.exists():raise FileExistsError(out)
    source=Path('outputs/multiscale_dataset_20261020/dataset')
    raster=json.loads((source/'raster_manifest.json').read_text())
    real=json.loads((ROOT/'manifest.json').read_text())['records']
    real=[r for r in real if r['status']=='included' and r['split']=='train']
    synth=[r for r in raster['images'] if r['split']=='train']
    rank=lambda s:hashlib.sha256((str(SEED)+s).encode()).hexdigest()
    real=sorted(real,key=lambda r:rank(str(r['source_row'])))[:384]
    synth=sorted(synth,key=lambda r:rank(r['image']))[:96]
    assert len(real)==384 and len(synth)==96
    manifest=[];counts={'real':Counter(),'synthetic':Counter()}
    for folder in ('images/train','labels/train'):(out/folder).mkdir(parents=True,exist_ok=True)
    for r in real:
        image=ROOT/r['image'];label=ROOT/r['label']
        shutil.copy2(image,out/'images/train'/image.name);shutil.copy2(label,out/'labels/train'/label.name)
        for line in label.read_text().splitlines():counts['real'][int(line.split()[0])]+=1
        manifest.append({'domain':'real','source_row':r['source_row'],'image':image.name,'image_sha256':sha(image),'label_sha256':sha(label)})
    for r in synth:
        if not set(r['seeds']).issubset({814200,814201,814202,814203}):raise ValueError('Nontraining synthetic seed')
        image=source/r['image'];mask_path=source/r['mask'];mask=cv2.imread(str(mask_path),cv2.IMREAD_UNCHANGED)
        if mask is None:raise ValueError('Missing native mask')
        h,w=mask.shape;assert [w,h]==r['image_size']
        known={int(i['mask_id']) for i in r['instances']}
        assert set(map(int,np.unique(mask)))-{0}==known
        labels=[]
        for instance in r['instances']:
            y,x=np.where(mask==instance['mask_id'])
            assert len(x)==instance['pixels'] and len(x)>0
            x1,y1,x2,y2=int(x.min()),int(y.min()),int(x.max())+1,int(y.max())+1
            assert [x1,y1,x2,y2]==instance['bbox']
            cid=int(instance['class_id']);assert cid in (0,1,2)
            labels.append(f'{cid} {(x1+x2)/2/w:.9f} {(y1+y2)/2/h:.9f} {(x2-x1)/w:.9f} {(y2-y1)/h:.9f}')
            counts['synthetic'][cid]+=1
        name='synthetic_'+image.stem
        shutil.copy2(image,out/'images/train'/(name+image.suffix))
        label=out/'labels/train'/(name+'.txt');label.write_text('\n'.join(labels)+'\n')
        manifest.append({'domain':'synthetic','image':name+image.suffix,'source_image':str(image),
                         'image_sha256':sha(image),'label_sha256':sha(label),'mask_sha256':sha(mask_path),
                         'seeds':r['seeds'],'scene':r['scene'],'classes':'existing provisional calyx appearance mapping'})
    (out/'data.yaml').write_text('path: '+out.resolve().as_posix()+'\ntrain: images/train\nval: '+(ROOT/'dataset/images/val').resolve().as_posix()+'\ntest: '+(ROOT/'dataset/images/test').resolve().as_posix()+'\nnames:\n  0: Pintona\n  1: Madura\n  2: Sobremadura\n',encoding='utf-8')
    evaluation_hashes={r['sha256'] for r in json.loads((ROOT/'manifest.json').read_text())['records'] if r.get('split') in ('val','test')}
    assert not evaluation_hashes.intersection(r['image_sha256'] for r in manifest)
    write(out/'manifest.json',{'seed':SEED,'source_raster_manifest_sha256':sha(source/'raster_manifest.json'),
          'image_counts':{'real':384,'synthetic':96},'annotation_counts':{k:dict(v) for k,v in counts.items()},
          'ratio_unit':'images, not instances','synthetic_semantics':'provisional appearance labels; no measured internal fruit maturity',
          'training_views_only':True,'native_mask_bbox_checks_passed':True,'cross_split_hash_overlap':0,'records':manifest})
    print({k:dict(v) for k,v in counts.items()})


if __name__=='__main__':main()
