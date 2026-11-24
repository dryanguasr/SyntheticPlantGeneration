"""Train-only exploratory dark-area screening; no biological stain inference.

Boxes are available, not real instance masks. A color-independent central ROI
and an approximate GrabCut mask are both retained to expose mask sensitivity.
L* cutoffs describe photographed darkness, not calibrated tissue pigmentation.
"""
from pathlib import Path
from collections import Counter,defaultdict
import argparse,math,statistics,sys,time,random
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts')]
from appearance_campaign import read,write,sha,require,NAMES
import numpy as np

THRESHOLDS=(25,35,45)


def darkness_metrics(rgb,mask):
    import cv2
    if not np.any(mask):raise ValueError('Empty region')
    lab=cv2.cvtColor(np.asarray(rgb,dtype=np.float32)/255,cv2.COLOR_RGB2Lab)
    light=lab[:,:,0];values=light[mask];p90=float(np.percentile(values,90))
    return dict(pixels=int(mask.sum()),lightness_median=float(np.median(values)),lightness_p90=p90,
        absolute_dark_fraction={str(t):float(np.mean(values<t)) for t in THRESHOLDS},
        relative_contrast_dark_fraction=float(np.mean(values<min(50,.6*p90))),
        relative_contrast_cutoff=min(50,.6*p90))


def central_mask(shape,rect):
    yy,xx=np.indices(shape[:2]);x,y,w,h=rect
    return ((xx-(x+w/2))/(.30*w))**2+((yy-(y+h/2))/(.35*h))**2<=1


def approximate_mask(rgb,rect,seed):
    import cv2
    x,y,w,h=rect;mask=np.zeros(rgb.shape[:2],np.uint8)
    mask[y:y+h,x:x+w]=cv2.GC_PR_FGD
    yy,xx=np.indices(mask.shape);sure=((xx-(x+w/2))/(.08*w))**2+((yy-(y+h/2))/(.10*h))**2<=1
    mask[sure]=cv2.GC_FGD
    cv2.setRNGSeed(seed)
    cv2.grabCut(np.ascontiguousarray(rgb[:,:,::-1]),mask,None,np.zeros((1,65)),np.zeros((1,65)),3,cv2.GC_INIT_WITH_MASK)
    binary=(mask==cv2.GC_FGD)|(mask==cv2.GC_PR_FGD)
    n,labels,stats,centres=cv2.connectedComponentsWithStats(binary.astype(np.uint8),8)
    if n<=1:raise ValueError('No foreground component')
    center=(int(y+h/2),int(x+w/2));component=int(labels[center])
    if not component:component=1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA]))
    return labels==component


def describe(values):
    a=np.asarray(list(values),float)
    return dict(n=len(a),min=float(a.min()),p10=float(np.percentile(a,10)),q25=float(np.percentile(a,25)),
        median=float(np.median(a)),q75=float(np.percentile(a,75)),p90=float(np.percentile(a,90)),max=float(a.max()),mean=float(a.mean()))


def selection(manifest):
    selected=[];paired=[];inputs=[]
    for row in manifest['records']:
        if row['split']!='train':continue
        for kind in ('image','label'):require(sha(row[kind])==row[kind+'_sha256'],'Training source changed')
        boxes=[list(map(float,line.split())) for line in Path(row['label']).read_text().splitlines()]
        targets=[(i,b) for i,b in enumerate(boxes) if int(b[0])==2]
        if not targets:continue
        inputs.append(row)
        for i,b in targets:selected.append(dict(row=row,box_index=i,box=b,role='all_train_Sobremadura'))
        ti,t=sorted(targets,key=lambda v:min(v[1][3:]))[len(targets)//2]
        for cl in (0,1):
            controls=[(i,b) for i,b in enumerate(boxes) if int(b[0])==cl]
            if not controls:continue
            def distance(v):
                b=v[1];spatial=math.hypot(b[1]-t[1],b[2]-t[2])
                return spatial+.3*abs(math.log(max(1e-8,min(b[3:]))/max(1e-8,min(t[3:]))))
            ci,c=min(controls,key=distance)
            selected.append(dict(row=row,box_index=ci,box=c,role='same_photo_nearby_size_control'))
            paired.append(dict(target=f"row_{row['source_row']:04d}_box_{ti:03d}",control=f"row_{row['source_row']:04d}_box_{ci:03d}",class_id=cl))
    return selected,paired,inputs


def run(manifest_path,out):
    import cv2
    from PIL import Image,ImageDraw,ImageFont
    cv2.setNumThreads(2);started=time.time();out.mkdir(parents=True,exist_ok=False)
    selected,pairs,inputs=selection(read(manifest_path));require(sum(x['box'][0]==2 for x in selected)==363,'Unexpected training class2 inventory')
    write(out/'input_lock.json',dict(manifest=str(manifest_path),manifest_sha256=sha(manifest_path),
        records=inputs,only_split='train',selection='All363 class2; one nearby similar-size control of each available class per target image',pairs=pairs,
        ignored_val_and_test=True,script_sha256=sha(__file__),seed=20261031,parameter_preset='exploratory_Lstar25_35_45_core_and_grabcut'))
    results=[];cached_path=None;image=None
    for index,s in enumerate(selected):
        row=s['row'];identifier=f"row_{row['source_row']:04d}_box_{s['box_index']:03d}"
        if cached_path!=row['image']:
            with Image.open(row['image']) as im:image=np.asarray(im.convert('RGB'));cached_path=row['image']
        h,w=image.shape[:2];cid,cx,cy,bw,bh=s['box']
        x1=max(0,int(math.floor((cx-bw/2)*w)));y1=max(0,int(math.floor((cy-bh/2)*h)))
        x2=min(w,int(math.ceil((cx+bw/2)*w)));y2=min(h,int(math.ceil((cy+bh/2)*h)))
        pad=max(3,round(.12*max(x2-x1,y2-y1)));left,top=max(0,x1-pad),max(0,y1-pad)
        right,bottom=min(w,x2+pad),min(h,y2+pad);native=image[top:bottom,left:right]
        scale=min(1,224/max(native.shape[:2]));ww=max(8,round(native.shape[1]*scale));hh=max(8,round(native.shape[0]*scale))
        work=cv2.resize(native,(ww,hh),interpolation=cv2.INTER_AREA) if scale<1 else native.copy()
        # Use actual resize ratios after rounding.
        sx,sy=work.shape[1]/native.shape[1],work.shape[0]/native.shape[0]
        rect=(max(1,round((x1-left)*sx)),max(1,round((y1-top)*sy)),max(2,round((x2-x1)*sx)),max(2,round((y2-y1)*sy)))
        rx,ry,rw,rh=rect;rect=(rx,ry,min(rw,work.shape[1]-rx-1),min(rh,work.shape[0]-ry-1))
        core=central_mask(work.shape,rect);metrics=darkness_metrics(work,core);flags=[];gc=None;gc_metrics=None
        try:
            gc=approximate_mask(work,rect,20261031+index);gc_metrics=darkness_metrics(work,gc)
            ratio=int(gc.sum())/max(1,rect[2]*rect[3])
            if not .25<=ratio<=.95:flags.append('approximate_mask_area_extreme')
            if abs(gc_metrics['absolute_dark_fraction']['35']-metrics['absolute_dark_fraction']['35'])>.20:flags.append('mask_choice_changes_dark_fraction_over20pp')
        except (ValueError,cv2.error) as e:flags.append('grabcut_failed:'+type(e).__name__)
        if min(x2-x1,y2-y1)<12:flags.append('small_native_box')
        folder=out/'objects'/identifier;folder.mkdir(parents=True)
        Image.fromarray(native).save(folder/'crop.png')
        Image.fromarray(core.astype(np.uint8)*255).save(folder/'core.png')
        if gc is not None:Image.fromarray(gc.astype(np.uint8)*255).save(folder/'approximate_mask.png')
        light=cv2.cvtColor(work.astype(np.float32)/255,cv2.COLOR_RGB2Lab)[:,:,0]
        overlay=work.copy();region=core if gc is None else gc;dark=region&(light<35)
        overlay[dark]=(.6*overlay[dark]+.4*np.array([220,0,200])).astype(np.uint8)
        contour=np.zeros(work.shape[:2],np.uint8)
        if gc is not None:cv2.drawContours(overlay,cv2.findContours(gc.astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0],-1,(0,255,80),1)
        cv2.drawContours(overlay,cv2.findContours(core.astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0],-1,(0,200,255),1)
        Image.fromarray(overlay).save(folder/'overlay.png')
        record=dict(id=identifier,class_id=int(cid),class_name=NAMES[int(cid)],role=s['role'],source_row=row['source_row'],
            group_id=row['group_id'],source_image=row['image'],source_label=row['label'],box_index=s['box_index'],yolo_box=s['box'],
            crop_bounds_original=[left,top,right,bottom],box_xyxy_original=[x1,y1,x2,y2],native_box_min_side=min(x2-x1,y2-y1),
            work_shape=list(work.shape),box_rect_work=list(rect),core=metrics,approximate_surface=gc_metrics,flags=flags,
            mask_is_ground_truth=False,proximal_orientation='unannotated_not_assumed',folder=str(folder))
        write(folder/'measurement.json',record);results.append(record)
        if (index+1)%50==0:print('Measured',index+1,'/',len(selected),flush=True)
    summaries={}
    for cl in (0,1,2):
        rows=[r for r in results if r['class_id']==cl];valid=[r for r in rows if r['approximate_surface'] is not None]
        summaries[NAMES[cl]]=dict(n_boxes=len(rows),n_images=len({r['source_row'] for r in rows}),n_groups=len({r['group_id'] for r in rows}),
            core={str(t):describe(r['core']['absolute_dark_fraction'][str(t)] for r in rows) for t in THRESHOLDS},
            approximate_surface={str(t):describe(r['approximate_surface']['absolute_dark_fraction'][str(t)] for r in valid) for t in THRESHOLDS},
            candidate_nearly_all_dark_core=sum(r['core']['absolute_dark_fraction']['35']>=.8 for r in rows),
            candidate_nearly_all_dark_surface=sum(r['approximate_surface']['absolute_dark_fraction']['35']>=.8 for r in valid),
            flags=dict(Counter(f for r in rows for f in r['flags'])))
    lookup={r['id']:r for r in results};paired={}
    for cl in (0,1):
        p=[x for x in pairs if x['class_id']==cl]
        paired[NAMES[cl]]=dict(n=len(p),core_dark35_difference_Sobremadura_minus_control=describe(
            lookup[x['target']]['core']['absolute_dark_fraction']['35']-lookup[x['control']]['core']['absolute_dark_fraction']['35'] for x in p))
    write(out/'measurements.json',results)
    write(out/'summary.json',dict(classes=summaries,paired_same_photo=paired,wall_seconds=time.time()-started,
        thresholds_Lstar=list(THRESHOLDS),only_train=True,segmentation_human_validated=False,
        limits='Observed RGB darkness includes pigmentation, lighting shadows, veins, occluders and segmentation error; not physiological stain area. Core describes a box-center ROI, not whole calyx. GrabCut is approximate and may discard dark tissue. No anatomical proximal direction assumed.'))
    # Review low/mid/high bins and segmentation-sensitive cases, keeping group diversity.
    target=[r for r in results if r['class_id']==2];review=[]
    for low,high in ((0,.05),(.05,.2),(.2,.5),(.5,.8),(.8,1.01)):
        candidates=[r for r in target if low<=r['core']['absolute_dark_fraction']['35']<high]
        candidates.sort(key=lambda r:(r['group_id'],r['id']));random.Random(20261031+int(low*100)).shuffle(candidates)
        review.extend(candidates[:6])
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',16)
    for page in range(math.ceil(len(review)/9)):
        cells=review[page*9:(page+1)*9];sheet=Image.new('RGB',(1440,990),'#efefe8');draw=ImageDraw.Draw(sheet)
        for i,r in enumerate(cells):
            x=(i%3)*480;y=(i//3)*330
            for j,name in enumerate(('crop.png','overlay.png')):
                with Image.open(Path(r['folder'])/name) as im:
                    im=im.convert('RGB');im.thumbnail((230,260));sheet.paste(im,(x+j*240+(230-im.width)//2,y+55))
            gc=r['approximate_surface']['absolute_dark_fraction']['35'] if r['approximate_surface'] else float('nan')
            draw.text((x+5,y+3),r['id']+f" · núcleo {r['core']['absolute_dark_fraction']['35']:.0%} / máscara {gc:.0%}",fill='black',font=font)
            draw.text((x+5,y+25),r['group_id']+' · '+str(r['flags'])[:45],fill='black',font=font)
        sheet.save(out/f'review_page_{page+1}.png')
    write(out/'review_selection.json',dict(ids=[r['id'] for r in review],selection='Up to6 in each darkness bin; seeded selection, no model predictions or val/test'))
    print('Finished train-only screening:',len(target),'Sobremadura and',len(results)-len(target),'same-photo controls',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('manifest',type=Path);p.add_argument('out',type=Path);a=p.parse_args();run(a.manifest.resolve(),a.out.resolve())
