"""RGB-only coarse vegetation ROI and native-resolution tiled calyx pilot.

The coarse ROI is a documented color heuristic for these synthetic soil scenes,
not a trained shrub detector. Never use annotation masks to select inference tiles.
Source pixels are cropped without interpolation; training letterboxing is explicit.
"""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2), encoding='utf-8')


def vegetation_roi(rgb):
    h, w = rgb.shape[:2]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    # Engineering heuristic frozen before held-out evaluation. Includes yellow-green.
    foreground = ((hsv[:, :, 0] >= 20) & (hsv[:, :, 0] <= 95) &
                  (hsv[:, :, 1] >= 45) & (hsv[:, :, 2] >= 20)).astype(np.uint8)
    foreground = cv2.morphologyEx(foreground, cv2.MORPH_CLOSE, np.ones((21, 21), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(foreground)
    accepted = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= 100]
    if not accepted:
        return [0, 0, w, h], 'full_frame_fallback_no_vegetation'
    yy, xx = np.where(np.isin(labels, accepted))
    return [max(0, int(xx.min())-48), max(0, int(yy.min())-48),
            min(w, int(xx.max())+49), min(h, int(yy.max())+49)], 'rgb_hsv_vegetation_union'


def tile_boxes(roi, width, height, size=384, stride=256):
    def positions(low, high, limit):
        first = max(0, min(low, limit-size))
        last = max(first, min(max(low, high-size), limit-size))
        return sorted(set([*range(first, last+1, stride), last]))
    return [[x, y, min(width, x+size), min(height, y+size)]
            for y in positions(roi[1], roi[3], height)
            for x in positions(roi[0], roi[2], width)]


def prepare(root):
    source = root/'field_pilot_v181/dataset'
    output = root/'field_closeup_v185'
    output.mkdir(exist_ok=False)
    data = output/'dataset'
    rows = json.loads((source/'raster_manifest.json').read_text())['images']
    result, audit = [], []
    for row in rows:
        if row['split'] == 'test':
            continue  # Test stays complete and is only used by final evaluation.
        assert sha(source/row['image']) == row['rgb_sha256']
        assert sha(source/row['mask']) == row['raster_sha256']
        rgb = np.array(Image.open(source/row['image']).convert('RGB'))
        native = np.array(Image.open(source/row['mask']))
        roi, method = vegetation_roi(rgb)
        boxes = tile_boxes(roi, rgb.shape[1], rgb.shape[0])
        for index, (x1,y1,x2,y2) in enumerate(boxes):
            crop = rgb[y1:y2,x1:x2].copy()
            mask = native[y1:y2,x1:x2].copy()
            instances = []
            for item in row['instances']:
                yy,xx = np.where(mask == item['mask_id'])
                if not len(xx):
                    continue
                instances.append(dict(item, bbox=[int(xx.min()),int(yy.min()),int(xx.max())+1,int(yy.max())+1],
                                      pixels=len(xx)))
            # Current raster trainer requires >=1 instance; retain the exclusion audit.
            if not instances:
                audit.append(dict(image=row['image'], box=[x1,y1,x2,y2], exclusion='empty_training_tile'))
                continue
            name = Path(row['image']).stem+f'_tile_{index:02d}.png'
            image_path = Path('images')/row['split']/name
            mask_path = Path('masks')/row['split']/name
            (data/image_path).parent.mkdir(parents=True,exist_ok=True)
            (data/mask_path).parent.mkdir(parents=True,exist_ok=True)
            Image.fromarray(crop).save(data/image_path)
            Image.fromarray(mask).save(data/mask_path)
            assert np.array_equal(np.array(Image.open(data/image_path)),crop)
            assert np.array_equal(np.array(Image.open(data/mask_path)),mask)
            assert set(np.unique(mask))-{0} == {i['mask_id'] for i in instances}
            result.append(dict(row,image=str(image_path),mask=str(mask_path),image_size=[x2-x1,y2-y1],
                               instances=instances,rgb_sha256=sha(data/image_path),raster_sha256=sha(data/mask_path),
                               source_image=row['image'],source_box=[x1,y1,x2,y2],roi=roi,roi_method=method))
    split_seeds = {s:sorted({v for r in result if r['split']==s for v in r['seeds']}) for s in ('train','val')}
    assert not set(split_seeds['train']) & set(split_seeds['val'])
    assert not set(range(914140,914146)) & {v for values in split_seeds.values() for v in values}
    write(data/'raster_manifest.json',dict(version='native-close-patches/185',images=result))
    write(data/'dataset_contract.json',dict(training_eligible=True,technical_only=True,
          label_source='lossless crops of original instance masks',seeds=split_seeds,excluded=audit))
    (data/'dataset.yaml').write_text(f'path: {data.resolve().as_posix()}\ntrain: images/train\nval: images/val\nnames:\n  0: pintona\n  1: madura\n  2: sobremadura\n')
    write(output/'input_audit.json',dict(images={s:sum(r['split']==s for r in result) for s in ('train','val')},
          instances={s:sum(len(r['instances']) for r in result if r['split']==s) for s in ('train','val')},
          pixel_and_mask_roundtrip_exact=True,source_geometry_changes=False,source_resolution=[1280,720],
          crop_resolution=[384,384],new_optical_detail=False,roi_uses_ground_truth=False,seeds=split_seeds,
          limitation='Close framing from native source pixels, not new near-camera renders; no trained shrub detector.'))
    print((output/'input_audit.json').read_text(),flush=True)


def deduplicate(candidates):
    """Exact original mask NMS using disjoint-box rejection and cached areas."""
    kept=[]
    for mask,label in sorted(candidates,key=lambda pair:pair[1]['confidence'],reverse=True):
        yy,xx=np.nonzero(mask)
        if not len(xx):continue
        box=(int(xx.min()),int(yy.min()),int(xx.max())+1,int(yy.max())+1)
        area=len(xx);duplicate=False
        for previous,_,other,other_area in kept:
            x1,y1=max(box[0],other[0]),max(box[1],other[1])
            x2,y2=min(box[2],other[2]),min(box[3],other[3])
            if x1>=x2 or y1>=y2:continue
            intersection=int(np.logical_and(mask[y1:y2,x1:x2],previous[y1:y2,x1:x2]).sum())
            union=area+other_area-intersection
            if intersection/max(1,union)>.45 or intersection/max(1,min(area,other_area))>.75:
                duplicate=True;break
        if not duplicate:kept.append((mask,label,box,area))
    return [(mask,label) for mask,label,_,_ in kept]


def evaluate(root, provisional=False, run_name='field_closeup_v185', version='185'):
    import torch
    from ultralytics import YOLO
    from evaluate_field_pilot import match, metrics, overlay
    torch.set_num_threads(2)
    source=root/'field_pilot_v181/dataset';output=root/run_name
    vis=output/'comparison';vis.mkdir(exist_ok=False)
    model=YOLO(output/'training/weights/last.pt')
    assert list(model.names.values()) == ['pintona','madura','sobremadura']
    rows=[r for r in json.loads((source/'raster_manifest.json').read_text())['images'] if r['split'] in ('val','test')]
    frames=[]
    for row in rows:
        assert sha(source/row['image'])==row['rgb_sha256']
        assert sha(source/row['mask'])==row['raster_sha256']
        rgb=np.array(Image.open(source/row['image']).convert('RGB'));h,w=rgb.shape[:2]
        roi,method=vegetation_roi(rgb);tiles=tile_boxes(roi,w,h)
        candidates=[]
        for tile_index,(x1,y1,x2,y2) in enumerate(tiles):
            result=model.predict(rgb[y1:y2,x1:x2,::-1].copy(),imgsz=960,rect=False,conf=.25,
                                 retina_masks=True,max_det=300,device=0,verbose=False)[0]
            if result.masks is None:continue
            for mask,cl,score in zip(result.masks.data.cpu().numpy(),result.boxes.cls.cpu().tolist(),result.boxes.conf.cpu().tolist()):
                full=np.zeros((h,w),bool);full[y1:y2,x1:x2]=mask.astype(bool)
                if full.any():candidates.append((full,dict(class_id=int(cl),confidence=float(score),tile=tile_index)))
        # Same frozen overlap thresholds, bounded to intersecting bounding boxes.
        kept=deduplicate(candidates)
        masks=np.stack([m for m,_ in kept]) if kept else np.zeros((0,h,w),bool)
        labels=[label for _,label in kept]
        native=np.array(Image.open(source/row['mask']))  # evaluator only
        counts,matches,missed=match(native,row['instances'],masks,labels)
        coverage=np.zeros((h,w),bool)
        for x1,y1,x2,y2 in tiles:coverage[y1:y2,x1:x2]=True
        native_pixels=int((native>0).sum())
        frame=dict(image=Path(row['image']).stem,split=row['split'],roi=roi,roi_method=method,tiles=tiles,
                   classes=counts,matches=matches,missed=missed,predictions=labels,
                   source_rgb_sha256=row['rgb_sha256'],source_mask_sha256=row['raster_sha256'],
                   truth_pixel_coverage=float(((native>0)&coverage).sum()/max(1,native_pixels)))
        frames.append(frame)
        shown=overlay(Image.fromarray(rgb),masks,labels);draw=ImageDraw.Draw(shown);draw.rectangle(roi,outline='white',width=2)
        shown.save(vis/f'{frame["image"]}_roi.jpg',quality=95)
        np.savez_compressed(vis/f'{frame["image"]}.npz',masks=masks)
        print(frame['image'],len(labels),'predictions',len(matches),'TP',flush=True)
    splits={}
    for split in ('val','test'):
        selected=[f for f in frames if f['split']==split]
        classes=[metrics({k:sum(f['classes'][cl][k] for f in selected) for k in ('tp','fp','fn')}) for cl in range(3)]
        splits[split]=dict(classes=classes,total=metrics({k:sum(c[k] for c in classes) for k in ('tp','fp','fn')}))
    write(output/'evaluation.json',dict(version=version,splits=splits,frames=frames,weights_sha256=sha(output/'training/weights/last.pt'),
          protocol='confidence .25; original native masks; class-aware mask IoU .50',roi_truth_input=False,
          training_status='interrupted_after_one_completed_epoch' if provisional else 'completed',
          provisional=provisional,development_test=True,metric_type='fixed-threshold precision/recall/F1, not AP'))
    html=['<meta charset="utf-8"><style>body{background:#182028;color:white;font:16px system-ui}img{width:100%}td{width:25%}</style>',
          '<h1>MÃƒÂ¡scaras originales Ã‚Â· V177 Ã‚Â· V184 amplia Ã‚Â· V185 ROI y parches</h1>',
          '<p>ROI blanca: heurÃƒÂ­stica RGB de vegetaciÃƒÂ³n, no detector entrenado. Parches de pÃƒÂ­xeles originales, sin detalle ÃƒÂ³ptico nuevo.</p>',
          '<pre>'+json.dumps(splits,indent=2)+'</pre><table>']
    for frame in frames:
        name=frame['image'];html.append(f'<tr><td colspan="4">{frame["split"]}: {name}</td></tr><tr>')
        for path in (f'../field_training_v184/comparison/{name}_truth.jpg',f'../field_training_v184/comparison/{name}_previous_v177.jpg',
                     f'../field_training_v184/comparison/{name}_new_v184.jpg',f'comparison/{name}_roi.jpg'):
            html.append(f'<td><a href="{path}"><img src="{path}"></a></td>')
        html.append('</tr>')
    (output/'comparison.html').write_text((''.join(html)+'</table>').replace('V185','V'+version),encoding='utf-8')
    for scene in ('validation','test'):
        name=scene+'_view_003'
        sheet=Image.new('RGB',(2560,1520),'#182028');draw=ImageDraw.Draw(sheet)
        panels=[(root/'field_training_v184/comparison'/f'{name}_truth.jpg','Mascaras originales'),
                (root/'field_training_v184/comparison'/f'{name}_previous_v177.jpg','V177 anterior'),
                (root/'field_training_v184/comparison'/f'{name}_new_v184.jpg','V184 vista completa'),
                (vis/f'{name}_roi.jpg','V185 ROI + parches - PROVISIONAL 1 epoca' if provisional else 'V185 ROI RGB + parches')]
        for index,(path,title) in enumerate(panels):
            x=(index%2)*1280;y=(index//2)*760
            draw.text((x+10,y+10),title.replace('V185','V'+version),fill='white');sheet.paste(Image.open(path),(x,y+35))
        sheet.save(output/f'{scene}_comparison.jpg',quality=95)
    print(json.dumps(splits),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('stage',choices=['prepare','evaluate']);parser.add_argument('--provisional',action='store_true');parser.add_argument('--run-name',default='field_closeup_v185');parser.add_argument('--version',default='185');args=parser.parse_args()
    prepare(args.root.resolve()) if args.stage=='prepare' else evaluate(args.root.resolve(),args.provisional,args.run_name,args.version)
