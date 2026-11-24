"""Static four-panel evidence from cached boxes; no browser or new inference."""
from pathlib import Path
import argparse,json,math,sys
from PIL import Image,ImageDraw,ImageFont
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'scripts'),str(REPO/'src')]
from appearance_campaign import read,write,sha
from diagnose_sobremadura_pilot import iou


def wrapped(path,prefix):
    text=path.read_text(encoding='utf-8');assert prefix in text
    return json.loads(text.split(prefix,1)[1].removesuffix(';'))


def dash(draw,box,color,width=2,step=8):
    x1,y1,x2,y2=box
    for a,b in (((x1,y1),(x2,y1)),((x1,y2),(x2,y2)),((x1,y1),(x1,y2)),((x2,y1),(x2,y2))):
        length=math.dist(a,b)
        if not length:continue
        for t in range(0,math.ceil(length),step*2):
            stop=min(t+step,length)
            draw.line((a[0]+(b[0]-a[0])*t/length,a[1]+(b[1]-a[1])*t/length,
                       a[0]+(b[0]-a[0])*stop/length,a[1]+(b[1]-a[1])*stop/length),fill=color,width=width)


def render(root):
    meta=wrapped(root/'gallery_data.js','window.GALLERY=')
    current=read(REPO/'outputs/daylight_augmentation_115_20261112/pilot/real_manifest.json')
    sources={r['source_row']:r for r in current['records'] if r['split']=='test'}
    (root/'samples').mkdir(exist_ok=True)
    font=ImageFont.truetype('arial.ttf',20);small=ImageFont.truetype('arial.ttf',15);tiny=ImageFont.truetype('arial.ttf',13)
    colors=meta['class_colors'];threshold=meta['threshold'];proof=[]
    for case in meta['cases']:
        rid=case['row'];row=next(r for r in meta['rows'] if r['id']==rid);seed=case['seed'];focus=case['bbox']
        data=wrapped(root/'data'/f'seed_{seed}.js',f'window.MODEL_DATA[{seed}]=')
        source=sources[rid];assert sha(source['image'])==row['source_image_sha256']
        image=Image.open(source['image']).convert('RGB');w,h=image.size
        pad=.65*max(focus[2]-focus[0],focus[3]-focus[1]);cropbox=(max(0,int(focus[0]-pad)),max(0,int(focus[1]-pad)),min(w,math.ceil(focus[2]+pad)),min(h,math.ceil(focus[3]+pad)))
        crop=image.crop(cropbox);scale=min(684/crop.width,495/crop.height)
        crop=crop.resize((round(crop.width*scale),round(crop.height*scale)),Image.Resampling.LANCZOS)
        sx=crop.width/(cropbox[2]-cropbox[0]);sy=crop.height/(cropbox[3]-cropbox[1])
        target=max(row['truth'],key=lambda t:iou(focus,t['bbox']))
        canvas=Image.new('RGB',(1440,1480),'#f4f1e9');draw=ImageDraw.Draw(canvas)
        draw.text((20,12),f"Fila {rid} · semilla {seed} · etiqueta del objetivo: {meta['names'][target['class_id']]}",font=font,fill='#193b36')
        draw.text((20,43),'Referencias de octubre + pareja reciente: inspeccion cualitativa, no comparacion causal de cuatro tratamientos.',font=small,fill='#7c6234')
        for index,m in enumerate(meta['models']):
            x=(index%2)*720;y=88+(index//2)*650;d=data[m['id']][str(rid)]
            draw.text((x+18,y+8),m['title']+' · '+m['date'],font=font,fill='#193b36')
            draw.text((x+18,y+36),m['detail'],font=small,fill='#617367')
            candidates=[p for p in d['predictions'] if iou(p[:4],target['bbox'])>=.5]
            best={cid:max((p[5] for p in candidates if p[4]==cid),default=None) for cid in range(3)}
            names=['Pintona','Madura','Sobre']
            desc=' | '.join(f'{names[cid]} {score:.3f}'+(' debajo' if score<threshold else '') for cid,score in sorted(best.items(),key=lambda t:-(t[1] or 0)) if score is not None)
            draw.text((x+18,y+63),desc or 'Sin caja guardada a IoU >=0,5 sobre el objetivo',font=small,fill='#193b36')
            px=x+18+(684-crop.width)//2;py=y+98
            canvas.paste(crop,(px,py))
            overlay=Image.new('RGBA',crop.size,(0,0,0,0));ink=ImageDraw.Draw(overlay);placed=[]
            def project(b):return((b[0]-cropbox[0])*sx,(b[1]-cropbox[1])*sy,(b[2]-cropbox[0])*sx,(b[3]-cropbox[1])*sy)
            def visible(b):return b[2]>=cropbox[0] and b[0]<=cropbox[2] and b[3]>=cropbox[1] and b[1]<=cropbox[3]
            for t in row['truth']:
                if not visible(t['bbox']):continue
                b=project(t['bbox']);ink.rectangle(b,outline='#122c23',width=4);dash(ink,b,'white',2)
            predictions=[p for p in d['predictions'] if p[5]>=threshold and visible(p[:4])]
            low_sobre=max((p for p in candidates if p[4]==2 and p[5]<threshold),key=lambda p:p[5],default=None)
            if low_sobre is not None and best[2]<threshold:predictions.append(low_sobre)
            for pred in sorted(predictions,key=lambda p:p[5]):
                b=project(pred[:4]);color=colors[pred[4]];low=pred[5]<threshold
                # A crop-sized transparent layer clips at the image boundary,
                # without drawing artificial box edges at clipped coordinates.
                if low:dash(ink,b,color,2)
                else:ink.rectangle(b,outline=color,width=2)
                text=f'{names[pred[4]]} {pred[5]:.3f}'+(' bajo' if low else '')
                tw=ink.textbbox((0,0),text,font=tiny)[2]
                tx=max(0,min(b[0],crop.width-tw-5));ty=max(0,min(b[1]+17*pred[4],crop.height-18))
                for attempt in range(12):
                    label=(tx,ty,tx+tw+5,ty+17)
                    if not any(label[0]<q[2] and label[2]>q[0] and label[1]<q[3] and label[3]>q[1] for q in placed):break
                    ty=min(crop.height-18,ty+18)
                placed.append((tx,ty,tx+tw+5,ty+17))
                ink.rectangle((tx,ty,tx+tw+5,ty+17),fill=color);ink.text((tx+2,ty+1),text,font=tiny,fill='#10271e')
            canvas.paste(overlay,(px,py),overlay)
            n=sum(p[4]==2 and p[5]>=threshold for p in d['predictions'])
            label=f'Foto completa: Sobre >= {threshold:.4f}: {n} · TP {d["tp"]} / FP {d["fp"]} / FN {d["fn"]}'
            draw.text((x+18,y+605),label,font=small,fill='#193b36')
        draw.text((20,1400),'Blanco discontinuo: etiqueta original. Color solido: prediccion. Color discontinuo: Sobre bajo el umbral.',font=small,fill='#193b36')
        draw.text((20,1425),'Recorte elegido para diagnosticar errores; no estima su frecuencia ni adjudica anotaciones ausentes.',font=small,fill='#6c755e')
        path=root/'samples'/f'four_models_row_{rid}_seed_{seed}.png';canvas.save(path)
        proof.append(dict(row=rid,seed=seed,path=str(path.resolve()),sha256=sha(path),source_image_sha256=sha(source['image']),crop_xyxy=cropbox,models=4))
    write(root/'static_panels.json',dict(panels=proof,no_inference=True,no_training=True,annotations_unchanged=True))
    print(root/'samples')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path)
    render(parser.parse_args().root.resolve())
