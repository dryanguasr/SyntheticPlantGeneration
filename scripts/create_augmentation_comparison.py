"""Display whole real and newly rendered images matched by apparent object size."""
import math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from augmentation_pilot import ROOT, read, write, sha


def main():
    out=ROOT/'visual_review_size_pairs';out.mkdir(exist_ok=True)
    real=[];synthetic=[]
    for row in read(ROOT/'geometry/real_train.json')['rows']:
        g=row['geometry'];sizes=[b['min_side_960'] for b in g['boxes']]
        real.append(dict(id=f"real_{row['source_row']}",image=row['image'],size=float(np.median(sizes)),
            count=len(sizes),aspect=g['width']/g['height'],source_row=row['source_row']))
    for capture in sorted((ROOT/'renders/captures').glob('*/view_*/capture.json')):
        if int(capture.parent.name.split('_')[-1])<6:continue
        image=capture.parent/'rgb.png'
        assert sha(image)==read(capture)['rgb_sha256']
        with Image.open(image) as im:w,h=im.size
        items=[v for k,v in read(capture.parent/'annotations_private.json')['items'].items() if k!='0' and v['visible_pixels']]
        if not items:continue
        sizes=[min(v['bbox_xywh'][2:])*960/max(w,h) for v in items]
        synthetic.append(dict(id=capture.parent.parent.name+'/'+capture.parent.name,image=str(image),
            size=float(np.median(sizes)),count=len(sizes),aspect=w/h,capture=str(capture)))
    pairs=[];used=set()
    for target in [28,56,95,150]:
        candidates=[]
        for s in synthetic:
            if s['id'] in used:continue
            for r in real:
                if r['id'] in used:continue
                difference=abs(s['size']/r['size']-1)
                aspect=abs(math.log(s['aspect']/r['aspect']))
                if difference>.08 or aspect>.12:continue
                score=abs(math.log(s['size']/target))+abs(math.log(r['size']/target))+aspect+difference
                candidates.append((score,r,s))
        if not candidates:raise RuntimeError('No comparable whole-frame pair for target')
        _,r,s=min(candidates,key=lambda x:x[0]);used.update([r['id'],s['id']])
        pairs.append(dict(real=r,synthetic=s,median_size_difference_percent=100*abs(s['size']/r['size']-1)))
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',23)
    small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',19)
    bold=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',26)
    for page in range(2):
        sheet=Image.new('RGB',(1320,1590),'#f2f4f5');draw=ImageDraw.Draw(sheet)
        draw.text((24,14),'Encuadres completos con tamaños aparentes comparables',font=bold,fill='#17212b')
        draw.text((24,51),'Mediana del lado menor de las cajas al escalar el lado mayor de la imagen a 960 px.',font=small,fill='#40505e')
        for i,pair in enumerate(pairs[page*2:page*2+2]):
            top=92+i*740
            for j,key in enumerate(['real','synthetic']):
                row=pair[key];left=20+j*660
                label='REAL · entrenamiento' if key=='real' else 'SINTÉTICA · nueva captura'
                draw.text((left,top),label,font=bold,fill='#17212b')
                draw.text((left,top+35),f"Mediana: {row['size']:.1f} px  |  {row['count']} instancias",font=font,fill='#40505e')
                image=Image.open(row['image']).convert('RGB')
                image=ImageOps.contain(image,(620,620))
                sheet.paste(image,(left+(620-image.width)//2,top+73+(620-image.height)//2))
                draw.text((left,top+695),row['id'],font=small,fill='#40505e')
        sheet.save(out/f'pares_{page+1}.jpg',quality=95)
    write(out/'pairs.json',dict(pairs=pairs,selection='Four train-only whole-frame pairs: median size within 8%, similar aspect ratio; density not matched.',
        images_cropped=False,display_longest_side=620,not_a_dataset_admission_decision=True))
    print([(p['real']['id'],p['synthetic']['id'],p['real']['size'],p['synthetic']['size']) for p in pairs])


if __name__=='__main__':main()
