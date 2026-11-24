"""Compose actual approval renders and preserve the source bank boundary."""
from pathlib import Path
import sys,json
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src')]
from uchuva_lsystem.nodal_automation import read,write,sha
from PIL import Image,ImageDraw,ImageFont
import numpy as np


def rendered_darkness(row,instance):
    """Visible RGB darkness under identical light, not a lesion area estimate."""
    mask=np.asarray(Image.open(row['mask']).convert('RGB'),dtype=np.uint32)
    color=read(Path(row['mask']).parent/'annotations.json')['palette'][str(instance['mask_id'])]
    region=np.all(mask==np.asarray(color),axis=2);result={}
    for key,path in (('original',row['original_image']),('preview',row['image'])):
        rgb=np.asarray(Image.open(path).convert('RGB'),dtype=float)[region]/255
        linear=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
        y=linear@np.array([.2126,.7152,.0722]);lstar=116*np.where(y>216/24389,np.cbrt(y),(24389/27*y+16)/116)-16
        result[key]={str(t):float(np.mean(lstar<t)) for t in (35,45)}
    return result


def report(out):
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',24)
    small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',20)
    organs=read(out/'organs_result.json');context=read(out/'context_result.json')
    names=['Madura: marca basal','Sobre actual','Sobre leve','Intermedia','Extensa','Avanzada venosa','Seca/decolorada']
    board=Image.new('RGB',(1960,900),'#eeeeea');draw=ImageDraw.Draw(board)
    for i,r in enumerate(organs['records']):
        y=i*450
        for j,name in enumerate(names):draw.text((j*280+8,y+10),name,font=small,fill='#202020')
        board.paste(Image.open(r['image']).convert('RGB').crop((0,120,1960,520)),(0,y+50))
    board.save(out/'shape_comparison.png')
    # Same source crop before/after: no invented or retouched pixels.
    board=Image.new('RGB',(1800,770),'#eeeeea');draw=ImageDraw.Draw(board)
    selected=[]
    for j,name in enumerate(('historical','light','intermediate','extensive','advanced_venous','dry_bleached')):
        choices=[(i['visible_pixels'],row,i) for row in context['records'] for i in row['instances']
            if i['instance_id'] in context['modified'] and context['modified'][i['instance_id']]['name']==name]
        _,row,instance=max(choices,key=lambda t:t[0]);x,y,w,h=instance['bbox_xywh']
        pad=max(w,h)*.2;box=(int(x-pad),int(y-pad),int(x+w+pad),int(y+h+pad))
        for k,path in enumerate((row['original_image'],row['image'])):
            crop=Image.open(path).convert('RGB').crop(box)
            factor=min(288/crop.width,310/crop.height)
            crop=crop.resize((round(crop.width*factor),round(crop.height*factor)),Image.Resampling.LANCZOS)
            board.paste(crop,(j*300+(300-crop.width)//2,k*360+48+(310-crop.height)//2))
        crop_names=['Sobre actual','Mancha leve','Intermedia','Extensa','Avanzada venosa','Marca proximal']
        draw.text((j*300+8,10),crop_names[j],font=small,fill='#202020')
        selected.append(dict(variant=name,view=row['view_id'],instance=instance,plan=context['modified'][instance['instance_id']],
            visible_rgb_dark_fraction_Lstar=rendered_darkness(row,instance)))
    draw.text((10,738),'Recortes ampliados. Arriba: original. Abajo: nueva superficie. Mismas máscaras y encuadre.',font=small,fill='#202020')
    board.save(out/'context_crops.png');write(out/'selected_examples.json',selected)
    baseline=read(out/'baseline.json');failures=[]
    for p,record in baseline['locks'].items():
        if sha(p)!=record['sha256']:failures.append(p)
        if record.get('files'):
            for f,h in read(p)['files'].items():
                if sha(f)!=h:failures.append(f)
    source=Path(read(out/'plan.json')['source'])
    for plant in read(source/'dataset/pool_lock.json')['plants']:
        for key in ('plant','admission'):
            if sha(plant[key])!=plant[key+'_sha256']:failures.append(plant[key])
    if failures:raise ValueError('Protected artifacts changed: '+str(failures[:5]))
    assert read(source/'pause_requested.json')['active']
    write(out/'review.json',dict(status='awaiting_user_visual_review',rendered_rgb_images=4,
        crop_views=2,organ_plates=2,bank_images_added=0,training_started=False,
        protected_sources_and_plants_verified=True,context_masks_and_instances_identical=True,
        geometry_change_scope='isolated hollow organ fixtures only',physiological_resorption='not established'))
    (out/'review.html').write_text('<meta charset="utf-8"><title>Revisión de sobremaduras</title><style>body{font-family:Arial;background:#eee}img{max-width:100%}</style><h1>Muestras pendientes de aprobación</h1><p>Sin ampliar el banco ni entrenar. Contracción: hipótesis visual; no demuestra reabsorción fisiológica.</p>'+''.join('<h2>'+title+'</h2><img src="'+path+'">' for title,path in [('Forma y tamaño','shape_comparison.png'),('Antes / después','context_crops.png')]+[(r['view_id'],r['view_id']+'/rgb.png') for r in context['records']]),encoding='utf-8')
    print(out/'review.html')


if __name__=='__main__':report(Path(sys.argv[1]).resolve())
