"""Audit every native mask pixel and profile camera calibration, without dropping small labels."""
import argparse
from collections import Counter
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageOps
from augmentation_pilot import ROOT, read, write, sha, image_geometry, summary, gate, link


def export():
    rows=[]
    for capture in sorted((ROOT/'renders/captures').glob('*/view_*/capture.json')):
        folder=capture.parent;meta=read(capture)
        assert meta['split']=='train'
        assert sha(folder/'rgb.png')==meta['rgb_sha256']
        assert sha(folder/'mask_calyx_crisp_v2.png')==meta['mask_sha256']
        ann=read(folder/'annotations_private.json');mapping=read(folder.parent/'class_mapping_private.json')
        raw=np.asarray(Image.open(folder/'mask_calyx_crisp_v2.png').convert('RGB'),dtype=np.uint32)
        h,w=raw.shape[:2];codes=raw[:,:,0]+256*raw[:,:,1]+65536*raw[:,:,2]
        unique,counts=np.unique(codes,return_counts=True);countmap=dict(zip(unique.tolist(),counts.tolist()))
        known={0};labels=[];instances=[]
        for key,item in ann['items'].items():
            if key=='0':continue
            r,g,b=ann['palette'][key];code=r+256*g+65536*b;known.add(code)
            assert countmap.get(code,0)==item['visible_pixels']
            if not item['visible_pixels']:continue
            assert item['semantic_class']=='calyx'
            cl=mapping[item['instance_id']]['class_id'];assert cl in (0,1,2)
            yy,xx=np.where(codes==code);x1,x2=int(xx.min()),int(xx.max()+1);y1,y2=int(yy.min()),int(yy.max()+1)
            labels.append([cl,(x1+x2)/(2*w),(y1+y2)/(2*h),(x2-x1)/w,(y2-y1)/h])
            instances.append(dict(id=item['instance_id'],class_id=cl,pixels=item['visible_pixels'],bbox=[x1,y1,x2,y2]))
        assert set(unique.tolist())<=known
        ident='synthetic_'+folder.parent.name+'_'+folder.name
        image=ROOT/'synthetic/images'/f'{ident}.png';label=ROOT/'synthetic/labels'/f'{ident}.txt'
        link(folder/'rgb.png',image);label.parent.mkdir(parents=True,exist_ok=True)
        content=''.join(str(int(row[0]))+' '+ ' '.join(f'{v:.10f}' for v in row[1:])+'\n' for row in labels)
        if label.exists():assert label.read_text()==content
        else:label.write_text(content)
        rows.append(dict(synthetic_id=ident,image=str(image),label=str(label),scene=folder.parent.name,
            split='train',capture=str(capture),geometry=image_geometry(image,labels),instances=instances,
            image_sha256=sha(image),label_sha256=sha(label)))
    write(ROOT/'synthetic/manifest.json',dict(rows=rows,summary=summary(rows),all_visible_labels_retained=True))
    real=read(ROOT/'geometry/real_train.json')['rows']
    write(ROOT/'geometry/synthetic_gate.json',gate(real,rows))
    thumbs=[]
    for row in rows[:24]:
        im=Image.open(row['image']).convert('RGB');draw=ImageDraw.Draw(im);w,h=im.size
        for b in row['geometry']['boxes']:
            x,y,bw,bh=b['x'],b['y'],b['width'],b['height']
            draw.rectangle(((x-bw/2)*w,(y-bh/2)*h,(x+bw/2)*w,(y+bh/2)*h),outline=['lime','orange','red'][b['class_id']],width=2)
        tile=Image.new('RGB',(320,270),'white');tile.paste(ImageOps.contain(im,(320,240)),(0,25))
        ImageDraw.Draw(tile).text((3,3),f"{row['synthetic_id']} n={row['geometry']['count']}",fill='black');thumbs.append(tile)
    if thumbs:
        sheet=Image.new('RGB',(320*4,270*((len(thumbs)+3)//4)),'white')
        for i,im in enumerate(thumbs):sheet.paste(im,((i%4)*320,(i//4)*270))
        sheet.save(ROOT/'geometry/synthetic_contact_sheet.jpg')
    print(summary(rows));print(gate(real,rows))


if __name__=='__main__':export()
