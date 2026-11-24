"""Prepare 30 random +20 difficult train images and fresh bounded proposals.

No training, renders or writes to the original dataset. CPU inference only;
the selected detector checkpoints have seen train, so this is not an accuracy
study on unseen data. Proposals stay private until a blind manual is saved.
"""
from pathlib import Path
from collections import Counter
import argparse, json, random, shutil, sys, time
from PIL import Image, ImageDraw, ImageFont
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts')]
from uchuva_annotation_audit.store import read,sha,atomic_json,iou,SessionLock
from appearance_campaign import verify_sources
from daylight_augmentation_pilot import generation_paused
CURRENT=REPO/'outputs/daylight_augmentation_115_20261112/pilot'
ROOT=REPO/'outputs/blind_annotation_50_20261113'
SEED=20261113


def labels(row,w,h):
    result=[]
    for j,line in enumerate(Path(row['label']).read_text().splitlines()):
        if not line.strip():continue
        c,x,y,bw,bh=map(float,line.split())
        result.append(dict(id=f'original_{j}',class_id=int(c),bbox=[(x-bw/2)*w,(y-bh/2)*h,(x+bw/2)*w,(y+bh/2)*h]))
    return result


def choose_rows(records,seed=SEED,exclude_rows=()):
    rng=random.Random(seed)
    excluded_hash={r['image_sha256'] for r in records if r['split']!='train'}
    excluded_groups={r['group_id'] for r in records if r['split']!='train'}
    train=[r.copy() for r in records if r['split']=='train' and r['source_row'] not in exclude_rows and r['image_sha256'] not in excluded_hash and r['group_id'] not in excluded_groups]
    # Hash unique even if a future manifest contains repeated files.
    train=list({r['image_sha256']:r for r in reversed(train)}.values())
    train.sort(key=lambda r:r['source_row'])
    random_rows=rng.sample(train,30);used={r['source_row'] for r in random_rows}
    for r in random_rows:r.update(stratum='random',selection_reason='uniform_random_train')
    pool=[r for r in train if r['source_row'] not in used]
    hard=[];groups=Counter()
    metrics={}
    for r in pool:
        with Image.open(r['image']) as im:w,h=im.size
        truth=labels(r,w,h);counts=Counter(t['class_id'] for t in truth)
        metrics[r['source_row']]=dict(sobre=counts[2],density=len(truth),
            small=sum(min(t['bbox'][2]-t['bbox'][0],t['bbox'][3]-t['bbox'][1])*960/max(w,h)<16 for t in truth),
            mixed=len(counts))
    for bucket in ('sobre','density','small','mixed'):
        available=[r for r in pool if r['source_row'] not in used]
        rng.shuffle(available)
        available.sort(key=lambda r:metrics[r['source_row']][bucket],reverse=True)
        selected=[]
        for r in available:
            if groups[r['group_id']]>=9:continue
            selected.append(r);groups[r['group_id']]+=1;used.add(r['source_row'])
            if len(selected)==5:break
        assert len(selected)==5
        for r in selected:r.update(stratum='difficult',selection_reason='ranked_'+bucket,selection_metrics=metrics[r['source_row']])
        hard.extend(selected)
    selected=random_rows+hard;rng.shuffle(selected)
    assert len(selected)==50 and len({r['image_sha256'] for r in selected})==50
    assert Counter(r['stratum'] for r in selected)=={'random':30,'difficult':20}
    return selected


def merged_objects(first,second):
    # Primary boxes from real+classical, then confident unmatched hybrid boxes.
    # Keep raw model output and disagreement in private evidence.
    result=[]
    for family,preds,threshold in [('real_classical',first,.25),('synthetic115_classical',second,.35)]:
        for p in sorted(preds,key=lambda p:-p['confidence']):
            if p['confidence']<threshold:continue
            if any(iou(p['bbox'],q['bbox'])>=.6 for q in result):continue
            result.append(dict(id=f'auto_{len(result):03}',class_id=p['class_id'],bbox=p['bbox'],
                confidence=p['confidence'],source=family,note='Propuesta inicial del detector; revisar visualmente'))
    return result


def prepare(root,seed=SEED,exclude_pilot=None):
    root=root.resolve();root.mkdir(exist_ok=True)
    generation_paused(CURRENT);verify_sources(CURRENT)
    if (root/'sealed.json').exists():raise ValueError('Piloto ya congelado; no se sobrescribe')
    lock=SessionLock(root/'preparation.lock')
    try:
        for folder in ('images','private/originals','private/proposals','private/raw','private/review_sheets'):(root/folder).mkdir(parents=True,exist_ok=True)
        manifest=read(CURRENT/'real_manifest.json');selection_path=root/'private/selection.json'
        if selection_path.exists():selected=read(selection_path)['samples']
        else:
            excluded=[] if exclude_pilot is None else [r['source_row'] for r in read(exclude_pilot/'private/selection.json')['samples']]
            selected=choose_rows(manifest['records'],seed,excluded)
            for n,row in enumerate(selected):row['id']=f'I{n+1:02}'
            atomic_json(selection_path,dict(seed=seed,samples=selected,sampling='30 uniform random then20 ranked difficult, five per bucket; shuffled blind queue',excluded_technical_pilot=str(exclude_pilot),excluded_source_rows=excluded))
        public=[];inputs={str(CURRENT/'real_manifest.json'):sha(CURRENT/'real_manifest.json')}
        for row in selected:
            assert row['split']=='train'
            for kind in ('image','label'):
                assert sha(row[kind])==row[kind+'_sha256'];inputs[row[kind]]=row[kind+'_sha256']
            ident=row['id'];target=root/'images'/f'{ident}.jpg'
            if not target.exists():shutil.copy2(row['image'],target)
            assert sha(target)==row['image_sha256']
            with Image.open(target) as im:w,h=im.size
            public.append(dict(id=ident,image=f'images/{ident}.jpg',width=w,height=h))
            atomic_json(root/'private/originals'/f'{ident}.json',dict(objects=labels(row,w,h),label_sha256=row['label_sha256'],source_row=row['source_row']))
        atomic_json(root/'samples.json',dict(version='blind-audit/1',samples=public))
        authorization=dict(user_authorized='50 training images, random+difficult, preserve originals, manual first then compare',
            seed=seed,images=50,random=30,difficult=20,original_labels_immutable=True,no_training=True,no_plant_renders=True,
            new_inference='CPU only, two existing checkpoint detectors for initial localization; then Codex visual review',
            cutoff=dict(real_classical=.25,synthetic115_classical_unmatched=.35,provenance='engineering_heuristic prelabel cutoff, not a changed training policy'),
            held_out_images_used=False,held_out_groups_used=False,training_seen_by_detectors=True,
            expected_final_status='ready_for_blind_human_audit',human_audit_not_yet_run=True)
        atomic_json(root/'authorization.json',authorization)
        import torch
        from ultralytics import YOLO
        torch.set_num_threads(4)
        evaluation=read(CURRENT/'evaluation_lock.json');raw={}
        for arm in ('real_classical','synthetic115_classical'):
            name=f'final_{arm}_20261022';weight=CURRENT/'training'/name/'weights/best.pt'
            assert sha(weight)==evaluation['weights'][name]
            inputs[str(weight)]=sha(weight);model=None
            for row in selected:
                ident=row['id'];path=root/'private/raw'/f'{ident}_{arm}.json'
                if path.exists():
                    cache=read(path);assert cache['image_sha256']==row['image_sha256'] and cache['weight_sha256']==sha(weight)
                else:
                    if model is None:model=YOLO(weight)
                    started=time.monotonic()
                    prediction=model.predict(str(root/'images'/f'{ident}.jpg'),imgsz=960,device='cpu',conf=.01,iou=.7,max_det=300,verbose=False)[0]
                    preds=[dict(class_id=int(cid),confidence=float(score),bbox=[float(v) for v in box]) for box,cid,score in zip(prediction.boxes.xyxy.cpu().tolist(),prediction.boxes.cls.cpu().tolist(),prediction.boxes.conf.cpu().tolist())]
                    cache=dict(image_sha256=row['image_sha256'],weight_sha256=sha(weight),predictions=preds,seconds=time.monotonic()-started,inference_device='cpu')
                    atomic_json(path,cache)
                raw[(ident,arm)]=cache['predictions']
                print('infer',ident,arm,flush=True)
            del model
        for row in selected:
            ident=row['id'];path=root/'private/proposals'/f'{ident}.json'
            if not path.exists():atomic_json(path,dict(objects=merged_objects(raw[(ident,'real_classical')],raw[(ident,'synthetic115_classical')]),
                method='detector localization + pending Codex visual review',review_state='pending',reviewer='not_human',training_seen_by_detectors=True))
        atomic_json(root/'private/input_lock.json',dict(files=inputs))
        if exclude_pilot is None:render_sheets(root,public)
        atomic_json(root/'state.json',dict(stage='proposals_pending_codex_review',total=50,human_manual_completed=0,generation_paused=True,pilot_training_paused=True))
    finally:lock.close()


def render_sheets(root,public):
    colors=['#00ef8c','#ffd14a','#ff4dc3','#aaaaaa']
    for start in range(0,50,4):
        sheet=Image.new('RGB',(1800,1500),'#f5f2eb');draw=ImageDraw.Draw(sheet);font=ImageFont.truetype('arial.ttf',22)
        for j,s in enumerate(public[start:start+4]):
            im=Image.open(root/s['image']).convert('RGB');proposal=read(root/'private/proposals'/f'{s["id"]}.json');d=ImageDraw.Draw(im)
            f=ImageFont.truetype('arial.ttf',max(14,im.width//65))
            for k,p in enumerate(proposal['objects']):
                cid=p['class_id'];color=colors[cid if cid is not None else 3]
                d.rectangle(p['bbox'],outline=color,width=3);d.text((p['bbox'][0],p['bbox'][1]),f'{k}:{["P","M","S","?"][cid if cid is not None else 3]}',font=f,fill='white',stroke_width=2,stroke_fill='black')
            x=(j%2)*900;y=(j//2)*750;draw.text((x+10,y+7),f'{s["id"]} | {len(proposal["objects"])} propuestas',font=font,fill='#173d37')
            im.thumbnail((875,700));sheet.paste(im,(x+10+(875-im.width)//2,y+40+(700-im.height)//2))
        sheet.save(root/'private/review_sheets'/f'proposals_{start//4+1:02}.jpg',quality=94)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--seed',type=int,default=SEED);parser.add_argument('--exclude-pilot',type=Path)
    args=parser.parse_args();prepare(args.root,args.seed,args.exclude_pilot)
