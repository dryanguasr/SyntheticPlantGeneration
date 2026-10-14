"""Create an immutable small development audit, without opening reserved images."""
import hashlib
import json
from pathlib import Path
import random
import sys
import xml.etree.ElementTree as ET

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uchuva_lsystem.segmentation_cycles import write, sha


def main():
    root = ROOT / 'outputs/integral_diagnosis_20261014'
    root.mkdir(exist_ok=True)
    if (root/'status.json').exists():raise FileExistsError('Preparation already completed')
    previous = ROOT / 'outputs/continuous_row_20261008'
    run = json.loads((previous / 'run.json').read_text())
    write(root / 'run.json', dict(version='integral-diagnosis/1.0', seed=20261014,
        parameter_preset='controlled_integral_development', classes=run['classes'],
        model=run['model'], model_sha256=run['model_sha256'],
        minimum_runtime_free_memory_gib=2, minimum_start_free_memory_gib=6.5,
        training='synthetic_only', pose='RGB_ArUco_vs_noisy_relative_motion',
        previous_campaign=str(previous), status='audit_and_small_tests'))
    write(root / 'effective_budget.json', dict(version='effective-execution-budget/1.0',
        limit_seconds=None, historical_execution_seconds=0))
    (root / 'execution_jobs').mkdir(exist_ok=True)
    (root / 'controller_sessions').mkdir(exist_ok=True)
    # Conservative reservation: reject seeds appearing anywhere in prior JSON records.
    seeds = list(range(914140, 914146))
    conflicts = []
    inventory_paths=set()
    for pattern in ('*/run.json','*/*split*.json','*/*seed*.json','*/morphologies.json','*/*/morphologies.json'):
        inventory_paths.update((ROOT/'outputs').glob(pattern))
    for p in sorted(inventory_paths):
        if root in p.parents or not any(s in p.name.lower() for s in ('morpholog','run.json','partition','split','seed','manifest')) or p.stat().st_size > 30_000_000:
            continue
        text = p.read_text(encoding='utf-8-sig', errors='replace')
        import re
        if any(re.search(r'(?<![\d.])'+str(seed)+r'(?![\d.])',text) for seed in seeds):
            conflicts.append(str(p))
    write(root / 'reserved_seeds.json', dict(seeds=seeds, generated=False,
        inspection_allowed=False, scan_conflicts=conflicts,
        limitation='Preliminary scan of named inventories <=30MB; validate actual morphology seed sets before final generation'))
    new = ROOT / 'outputs/new_real_dataset/captura_20260912_v6'
    rows = [json.loads(line) for line in (new / 'manifest.jsonl').open(encoding='utf-8')]
    candidates = [r for r in rows if r['split']=='train' and r['selection']=='include']
    random.Random(20261014).shuffle(candidates)
    chosen=[]; sources={}
    # Spread sources and reject temporally adjacent frames; no fake plant IDs.
    for row in candidates:
        times=sources.setdefault(row['source_id'], [])
        t=row.get('timestamp_seconds')
        if len(times)>=3 or (t is not None and any(x is not None and abs(t-x)<10 for x in times)):
            continue
        path=new/'images/train'/f"{row['image_id']}.jpg"
        if not path.exists():
            path=new/row['candidate_path']
        if not path.exists():continue
        times.append(t)
        chosen.append(dict(dataset='new',path=str(path),group=row['group_id'],
            source=row['source'],timestamp_seconds=t,rotation_cw=row['rotation_cw'],
            plant_id=None,view_category='pending_visual_review'))
        if len(chosen)==60:break
    old=list((ROOT/'Dataset Original/IMAGENES/train').glob('*.jpg'))
    old.sort(key=lambda p:hashlib.sha256(p.name.encode()).hexdigest())
    chosen += [dict(dataset='old',path=str(p),group=None,plant_id=None,
        view_category='pending_visual_review',rotation_cw=0) for p in old[:60]]
    atlas=root/'atlas';atlas.mkdir(exist_ok=True)
    for dataset in ('new','old'):
        subset=[r for r in chosen if r['dataset']==dataset]
        for start in range(0,len(subset),12):
            sheet=np.full((900,1200,3),245,np.uint8)
            for j,row in enumerate(subset[start:start+12]):
                im=cv2.imread(row['path']);h,w=im.shape[:2]
                row.update(width=w,height=h,sha256=sha(Path(row['path'])))
                scale=min(300/w,260/h);im=cv2.resize(im,(round(w*scale),round(h*scale)))
                x=(j%4)*300;y=(j//4)*300
                sheet[y:y+im.shape[0],x:x+im.shape[1]]=im
                cv2.putText(sheet,f'{dataset} {start+j:02d}',(x+8,y+285),0,.55,(20,20,20),1)
            cv2.imwrite(str(atlas/f'{dataset}_{start:02d}.jpg'),sheet)
    write(atlas/'manifest.json',dict(selection='development train only; exploratory, category review pending',images=chosen))
    field=previous/'field_batched';tree=ET.parse(field/'field.sdf')
    paths={tag:sorted({e.text for e in tree.findall('.//'+tag)}) for tag in ('albedo_map','normal_map','roughness_map')}
    write(root/'material_audit.json',dict(source_sha256=sha(field/'field.sdf'),
        counts={tag:len(tree.findall('.//'+tag)) for tag in paths},
        unique_maps=paths,missing=[str(field/p) for values in paths.values() for p in values if not (field/p).exists()],
        conclusion='Normal maps absent; visual detection effect unmeasured'))
    # Fixed public sequence selection: twelve short blocks across the complete route.
    public=root/'public_screening';(public/'rgb').mkdir(parents=True,exist_ok=True)
    frames=json.loads((previous/'public/frames.json').read_text())
    indices=sorted({min(len(frames)-1,int(i)+offset) for i in np.linspace(0,len(frames)-5,12) for offset in range(5)})
    import shutil
    selected=[]
    for i in indices:
        row=frames[i];source=previous/'public/rgb'/row['filename']
        shutil.copy2(source,public/'rgb'/row['filename']);selected.append(row)
    write(public/'frames.json',selected)
    write(root/'screening_selection.json',dict(indices=indices,frames=len(indices),
        rule='12 evenly spaced blocks x 5 consecutive frames; no truth consulted',
        use='2D screening only, insufficient support for final 3D selection'))
    write(root/'queue_status.json',dict(state='completed',note='Preparation only'))
    write(root/'status.json',dict(state='audit_prepared',completed=False,
        pending=['visual_review','basal_fixture','materials_AB','perception_screening','identity_audit',
            'noisy_sensor_fusion','route_comparison','training_comparison','integration','reserved_evaluation','report']))
    print(root, flush=True)


if __name__=='__main__':main()
