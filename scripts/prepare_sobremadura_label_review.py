"""Read-only visual triage, not an automatic label adjudicator."""
from pathlib import Path
import sys,json,math
from collections import defaultdict
from PIL import Image,ImageDraw,ImageFont
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'scripts'),str(REPO/'src')]
from appearance_campaign import read,write,sha
from daylight_augmentation_pilot import generation_paused
from diagnose_sobremadura_pilot import iou
from render_four_model_review_panels import wrapped
GALLERY=REPO/'outputs/sobremadura_four_models_20261113'
ROOT=REPO/'outputs/suspected_sobremadura_labels_20261113'


def sheet(items,path,columns=3,cell=(600,520)):
    cw,ch=cell;im=Image.new('RGB',(cw*columns,ch*math.ceil(len(items)/columns)),'#f5f2eb')
    draw=ImageDraw.Draw(im);font=ImageFont.truetype('arial.ttf',19)
    for k,(image,title,subtitle) in enumerate(items):
        x=(k%columns)*cw;y=(k//columns)*ch
        draw.text((x+9,y+7),title,font=font,fill='#173d37')
        draw.text((x+9,y+31),subtitle,font=font,fill='#735e40')
        image=image.copy();image.thumbnail((cw-18,ch-68));im.paste(image,(x+9+(cw-18-image.width)//2,y+60+(ch-68-image.height)//2))
    im.save(path)


def main():
    generation_paused(REPO/'outputs/daylight_augmentation_115_20261112/pilot')
    lock=read(GALLERY/'input_lock.json')
    for p,h in lock['files'].items():
        if sha(p)!=h:raise ValueError(f'Frozen input changed: {p}')
    meta=wrapped(GALLERY/'gallery_data.js','window.GALLERY=')
    models={s:wrapped(GALLERY/'data'/f'seed_{s}.js',f'window.MODEL_DATA[{s}]=') for s in meta['seeds']}
    manifest=read(REPO/'outputs/daylight_augmentation_115_20261112/pilot/real_manifest.json')
    source={r['source_row']:r for r in manifest['records'] if r['split']=='test'}
    ROOT.mkdir(exist_ok=True);(ROOT/'overview').mkdir(exist_ok=True);(ROOT/'triage').mkdir(exist_ok=True)
    candidates=[];overview=[]
    for row in meta['rows']:
        rid=row['id'];original=Image.open(source[rid]['image']).convert('RGB')
        display=original.copy();d=ImageDraw.Draw(display);f=ImageFont.truetype('arial.ttf',max(16,original.width//65))
        for j,t in enumerate(row['truth']):
            b=t['bbox'];d.rectangle(b,outline=['#00ff70','#ffd000','#ff00cc'][t['class_id']],width=3)
            d.text((b[0],b[1]),f'{j}:{["P","M","S"][t["class_id"]]}',font=f,fill='white',stroke_width=2,stroke_fill='black')
        overview.append((display,f'Fila {rid} | {row["gt_sobre"]} GT Sobre',row['group']))
        all_s=[]
        for seed in meta['seeds']:
            for family in ('none','classical','synthetic','hybrid'):
                all_s.extend(dict(bbox=p[:4],confidence=p[5],seed=seed,family=family) for p in models[seed][family][str(rid)]['predictions'] if p[4]==2 and p[5]>=meta['threshold'])
        for j,t in enumerate(row['truth']):
            if t['class_id']==2:continue
            support=[p for p in all_s if iou(t['bbox'],p['bbox'])>=.5]
            if support:candidates.append(dict(id=f'r{rid}_gt{j}',row=rid,truth_index=j,actual_class=t['class_id'],bbox=t['bbox'],support=support,kind='other_class'))
        unmatched=[p for p in all_s if max((iou(p['bbox'],t['bbox']) for t in row['truth']),default=0)<.1]
        clusters=[]
        for p in sorted(unmatched,key=lambda x:-x['confidence']):
            match=next((c for c in clusters if iou(c[0]['bbox'],p['bbox'])>=.5),None)
            if match is None:clusters.append([p])
            else:match.append(p)
        for j,cluster in enumerate(clusters):
            candidates.append(dict(id=f'r{rid}_u{j}',row=rid,truth_index=None,actual_class=None,bbox=cluster[0]['bbox'],support=cluster,kind='low_overlap_candidate'))
    for i in range(0,len(overview),6):sheet(overview[i:i+6],ROOT/'overview'/f'photos_{i//6+1:02}.jpg',3,(600,620))
    for c in candidates:
        c['families']=sorted(set(p['family'] for p in c['support']))
        c['current_seed_support']=len(set(p['seed'] for p in c['support'] if p['family'] in ('classical','hybrid')))
        c['max_confidence']=max(p['confidence'] for p in c['support'])
    candidates.sort(key=lambda c:(-c['current_seed_support'],-len(c['families']),-c['max_confidence']))
    items=[]
    for n,c in enumerate(candidates):
        original=Image.open(source[c['row']]['image']).convert('RGB');b=c['bbox'];pad=.35*max(b[2]-b[0],b[3]-b[1])
        crop=(max(0,math.floor(b[0]-pad)),max(0,math.floor(b[1]-pad)),min(original.width,math.ceil(b[2]+pad)),min(original.height,math.ceil(b[3]+pad)))
        image=original.crop(crop);d=ImageDraw.Draw(image);d.rectangle((b[0]-crop[0],b[1]-crop[1],b[2]-crop[0],b[3]-crop[1]),outline='#ff00cc',width=2)
        c['review_order']=n;c['crop']=crop;c['crop_path']=str(ROOT/'triage'/f'{c["id"]}.jpg');image.save(c['crop_path'],quality=95)
        cls='Pintona' if c['actual_class']==0 else 'Madura' if c['actual_class']==1 else 'Sin caja proxima*'
        items.append((image,f'{n} {c["id"]} | GT {cls}',f'{len(c["families"])} familias | max S {c["max_confidence"]:.2f}'))
    for i in range(0,len(items),12):sheet(items[i:i+12],ROOT/'triage'/f'candidates_{i//12+1:02}.jpg',3,(500,390))
    write(ROOT/'candidates.json',dict(candidates=candidates,notes=['Model proposals only; no labels changed','Low overlap is not verified absence of an annotation; inspect containment and original photo'],source=source))
    write(ROOT/'input_lock.json',dict(files=lock['files']|{str(GALLERY/'gallery_data.js'):sha(GALLERY/'gallery_data.js')}|{str(GALLERY/'data'/f'seed_{s}.js'):sha(GALLERY/'data'/f'seed_{s}.js') for s in meta['seeds']},generation_paused=True))
    print(json.dumps(dict(photos=94,overview_sheets=math.ceil(len(overview)/6),candidates=len(candidates),candidate_sheets=math.ceil(len(items)/12))))


if __name__=='__main__':main()
