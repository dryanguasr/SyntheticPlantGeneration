"""Recover original polygons and make provisional visible masks from RGB.

GrabCut is an approximate segmentation candidate generator, NOT a rectangular
mask substitute or a ground truth source. Model boxes are prompts only.
"""
from pathlib import Path
import sys,json,shutil,time,math,argparse
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts')]
from uchuva_annotation_audit.store import read,sha,atomic_json,validate_objects
from uchuva_annotation_audit.masks import encode_mask,polygons_mask,mask_bbox,area,decode_mask
from daylight_augmentation_pilot import generation_paused
ROOT=REPO/'outputs/blind_annotation_50_20261113'
SOURCE=REPO/'outputs/datasets/union_anotadas_20261021_v1/source_latest.ndjson'


def segment_rgb(image,bbox):
    w,h=image.size;x1,y1,x2,y2=bbox
    pad=.15*max(x2-x1,y2-y1)+3
    roi=(max(0,math.floor(x1-pad)),max(0,math.floor(y1-pad)),min(w,math.ceil(x2+pad)),min(h,math.ceil(y2+pad)))
    part=image.crop(roi);pw,ph=part.size
    scale=min(1,256/max(pw,ph));small=part.resize((max(4,round(pw*scale)),max(4,round(ph*scale))))
    rgb=np.asarray(small);sh,sw=rgb.shape[:2]
    sx=sw/pw;sy=sh/ph
    b=(max(1,round((x1-roi[0])*sx)),max(1,round((y1-roi[1])*sy)),min(sw-1,round((x2-roi[0])*sx)),min(sh-1,round((y2-roi[1])*sy)))
    if b[2]-b[0]<3 or b[3]-b[1]<3:return None,'insufficient_prompt_area'
    mask=np.full((sh,sw),cv2.GC_PR_BGD,np.uint8)
    mask[b[1]:b[3],b[0]:b[2]]=cv2.GC_PR_FGD
    mask[0,:]=mask[-1,:]=mask[:,0]=mask[:,-1]=cv2.GC_BGD
    cx,cy=round((b[0]+b[2])/2),round((b[1]+b[3])/2)
    cv2.ellipse(mask,(cx,cy),(max(1,(b[2]-b[0])//10),max(1,(b[3]-b[1])//10)),0,0,360,cv2.GC_FGD,-1)
    try:cv2.grabCut(rgb,mask,None,np.zeros((1,65),np.float64),np.zeros((1,65),np.float64),3,cv2.GC_INIT_WITH_MASK)
    except cv2.error:return None,'grabcut_failed'
    binary=np.isin(mask,[cv2.GC_FGD,cv2.GC_PR_FGD]).astype(np.uint8)*255
    native=Image.fromarray(binary).resize((pw,ph),Image.Resampling.NEAREST)
    if native.getbbox() is None:return None,'empty_segmentation'
    full=Image.new('L',(w,h));full.paste(native,(roi[0],roi[1]))
    segmentation=encode_mask(full)
    return segmentation,'approximate_visible_rgb_grabcut'


def main():
    generation_paused(REPO/'outputs/daylight_augmentation_115_20261112/pilot')
    assert not (ROOT/'sealed.json').exists()
    revision=ROOT/'revisions/segmentation_correction_20261113';revision.mkdir(parents=True,exist_ok=True)
    for directory in ('originals','proposals'):
        backup=revision/f'box_{directory}'
        if not backup.exists():shutil.copytree(ROOT/'private'/directory,backup)
    if not (revision/'box_authorization.json').exists():shutil.copy2(ROOT/'authorization.json',revision/'box_authorization.json')
    rows=[json.loads(line) for line in SOURCE.read_text(encoding='utf-8').splitlines() if line.strip()]
    assert rows[0]['task']=='segment'
    download=read(SOURCE.parent/'download_manifest.json');assert sha(SOURCE)==download['source_sha256']
    selected=read(ROOT/'private/selection.json')['samples'];public=read(ROOT/'samples.json')['samples']
    sizes={s['id']:(s['width'],s['height']) for s in public}
    original_count=0;proposal_count=0;unresolved=0
    for row in selected:
        ident=row['id'];w,h=sizes[ident];raw=rows[row['source_row']-1]
        assert raw['file']==row['file'] and (raw['width'],raw['height'])==(w,h)
        objects=[]
        for j,segment in enumerate(raw['annotations']['segments']):
            points=[[x*w,y*h] for x,y in zip(segment[1::2],segment[2::2])]
            segmentation=encode_mask(polygons_mask([dict(role='outer',points=points)],w,h))
            objects.append(dict(id=f'original_{j}',class_id=int(segment[0]),segmentation=segmentation,
                bbox=mask_bbox(segmentation),bbox_source='native_mask_pixels',source_normalized_polygon=segment,
                rasterization='Pillow integer-coordinate polygon, visible region from original source'))
        atomic_json(ROOT/'private/originals'/f'{ident}.json',dict(objects=objects,source_row=row['source_row'],
            original_format='Ultralytics NDJSON segments',source_ndjson_sha256=sha(SOURCE),
            original_annotations=raw['annotations'],legacy_detection_label_sha256=row['label_sha256']))
        originals=revision/'box_proposals'/f'{ident}.json';old=read(originals)
        candidates=[];failed=[];image=Image.open(ROOT/'images'/f'{ident}.jpg').convert('RGB')
        for j,obj in enumerate(old['objects']):
            segmentation,status=segment_rgb(image,obj['bbox'])
            if segmentation is None:
                failed.append(dict(prompt=obj,status=status));continue
            candidates.append(dict(id=obj['id'],class_id=obj['class_id'],segmentation=segmentation,
                bbox=mask_bbox(segmentation),bbox_source='native_mask_pixels',confidence=obj['confidence'],
                detector_source=obj['source'],segmentation_method=status,
                note='Máscara automática RGB aproximada: revisar bordes, hojas oclusoras y clase',
                original_segmentation_used=False))
        validate_objects(candidates,w,h)
        atomic_json(ROOT/'private/proposals'/f'{ident}.json',dict(objects=candidates,unresolved_regions=failed,
            method='existing detectors for prompts + RGB GrabCut; pending Codex visual review',
            review_state='pending',original_geometry_used=False,training_seen_by_detectors=True))
        original_count+=len(objects);proposal_count+=len(candidates);unresolved+=len(failed)
        print(ident,'native masks',len(candidates),'original polygons',len(objects),flush=True)
    auth=read(ROOT/'authorization.json');auth.update(annotation_contract='instance_segmentation_native_mask_primary',
        bounding_boxes='derived_from_occupied_mask_pixels_only',segmentation_user_correction=True,
        original_segmentation='recovered verbatim from original NDJSON, immutable',
        proposals='approximate RGB masks prompted by detectors; never rectangular masks',
        disconnected_parts_and_holes_preserved=True,source_ndjson_sha256=sha(SOURCE))
    atomic_json(ROOT/'authorization.json',auth)
    lock=read(ROOT/'private/input_lock.json');lock['files'][str(SOURCE)]=sha(SOURCE);atomic_json(ROOT/'private/input_lock.json',lock)
    atomic_json(ROOT/'segmentation_preparation.json',dict(images=50,original_instances=original_count,proposed_masks=proposal_count,
        unresolved_regions=unresolved,labels_changed=False,geometry='native binary RLE; boxes derived',
        quality_status='provisional; automatic masks are not human-validated'))
    if not NO_REVIEW_SHEETS:render_sheets()


def render_sheets():
    public=read(ROOT/'samples.json')['samples'];folder=ROOT/'private/mask_review_sheets';folder.mkdir(exist_ok=True)
    for start in range(0,50,4):
        sheet=Image.new('RGB',(1800,1500),'#f5f2eb');d=ImageDraw.Draw(sheet);font=ImageFont.truetype('arial.ttf',23)
        for j,s in enumerate(public[start:start+4]):
            base=Image.open(ROOT/s['image']).convert('RGBA');overlay=Image.new('RGBA',base.size);draw=ImageDraw.Draw(overlay)
            proposal=read(ROOT/'private/proposals'/f'{s["id"]}.json')
            for k,p in enumerate(proposal['objects']):
                color=['#00ef8c','#ffd14a','#ff4dc3','#bbbbbb'][p['class_id'] if p['class_id'] is not None else 3]
                mask=decode_mask(p['segmentation']);paint=Image.new('RGBA',base.size,color);paint.putalpha(mask.point(lambda v:65 if v else 0));overlay=Image.alpha_composite(overlay,paint)
                b=p['bbox'];draw=ImageDraw.Draw(overlay)
                draw.text((b[0],b[1]),f'{k}:{["P","M","S","?"][p["class_id"] if p["class_id"] is not None else 3]}',font=font,fill='white',stroke_width=2,stroke_fill='black')
            image=Image.alpha_composite(base,overlay).convert('RGB');x=(j%2)*900;y=(j//2)*750
            d.text((x+10,y+7),s['id']+f' | {len(proposal["objects"])} mascaras propuestas',font=font,fill='#173d37')
            image.thumbnail((875,700));sheet.paste(image,(x+10+(875-image.width)//2,y+40+(700-image.height)//2))
        sheet.save(folder/f'masks_{start//4+1:02}.jpg',quality=95)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--no-review-sheets',action='store_true')
    args=parser.parse_args();ROOT=args.root.resolve();NO_REVIEW_SHEETS=args.no_review_sheets;main()
