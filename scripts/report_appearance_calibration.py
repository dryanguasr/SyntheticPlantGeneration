"""Auditable train/reference gallery and paired visual measurements, without inference."""
from __future__ import annotations
import argparse
import html
import json
from pathlib import Path
import sys
import hashlib
import shutil

import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageOps

REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'src'))
from uchuva_lsystem.appearance_profiles import CLASSES,BANKS,calibration_schedule


def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):Path(p).write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
FONT=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',20)
BOLD=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',25)
SMALL=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',16)


def tile(sheet,source,xy,size):
    image=ImageOps.contain(source,size)
    sheet.paste(image,(xy[0]+(size[0]-image.width)//2,xy[1]+(size[1]-image.height)//2))


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--attempt',required=True)
    p.add_argument('--previous');a=p.parse_args()
    root=a.root.resolve();attempt=root/'calibration'/a.attempt;out=attempt/'review';out.mkdir(exist_ok=True)
    refs=read(root/'references/real_instances.json');captures=[]
    completion=read(attempt/'completion.json')
    assert completion['complete'] and completion['captures']==50, 'Calibration incomplete'
    for path in sorted(attempt.glob('*/capture.json')):
        r=read(path);folder=path.parent
        assert sha(folder/'rgb.png')==r['rgb_sha256']
        assert sha(folder/'mask_calyx_crisp_v2.png')==r['mask_sha256']
        assert r['profiles_sha256']==sha(attempt/'profiles.json'), 'Round profiles changed after rendering'
        rgb=np.asarray(Image.open(folder/'rgb.png').convert('RGB'))/255
        mask=np.asarray(Image.open(folder/'mask_calyx_crisp_v2.png').convert('RGB'));valid=mask.max(2)>0
        if valid.any():
            lum=rgb[valid]@[.2126,.7152,.0722]
            r['photometry']={'target_luminance_median':float(np.median(lum)),'target_srgb_median':np.median(rgb[valid],axis=0).tolist(),
                'target_dark_fraction':float((lum<.02).mean()),'target_light_fraction':float((lum>.98).mean()),
                'context_luminance_median':float(np.median(rgb[~valid]@[.2126,.7152,.0722])) if (~valid).any() else None,
                'measurement':'visible calyx mask pixels; gamma-encoded sRGB, not reflectance'}
        else:r['photometry']={'empty_target_mask':True}
        if valid.any():
            pix=rgb[valid]
            r['photometry']['target_saturation_median']=float(np.median((pix.max(1)-pix.min(1))/np.maximum(pix.max(1),1e-6)))
        r['rgb']=str(folder/'rgb.png');captures.append(r)
    assert {r['view_id'] for r in captures}=={r['view_id'] for r in calibration_schedule()}
    groups={}
    for r in captures:
        key=(r['kind'],r['plant_index'],r['view'],r['class_id'],r['light'])
        groups.setdefault(key,[]).append(r)
    pairing=[]
    for key,rows in groups.items():
        assert len({r['geometry_sha256'] for r in rows})==1
        assert len({r['mask_sha256'] for r in rows})==1
        camera_hashes={sha(Path(r['rgb']).parent/'camera.json') for r in rows};assert len(camera_hashes)==1
        pairing.append({'group':list(key),'banks':[r['bank'] for r in rows],'geometry_equal':True,'mask_equal':True,'camera_equal':True})
    write(out/'visual_measurements.json',{'captures':captures,'paired_checks':pairing,'human_review':'pending','training_allowed':False})
    illustration=REPO/'Nuevo Dataset/Norma.webp'
    shutil.copy2(illustration,out/'ilustracion_aportada.webp')
    write(out/'illustration_provenance.json',{'source':str(illustration),'sha256':sha(illustration),
        'use':'referencia cualitativa aportada; no calibracion normativa ni asignacion de madurez interna'})
    # References are original pixels cropped only for display. No recoloring.
    panel=Image.new('RGB',(1440,1100),'#f2f1ec');draw=ImageDraw.Draw(panel)
    draw.text((24,16),'Referencias reales de entrenamiento — apariencia del capacho',font=BOLD,fill='#18372f')
    draw.text((24,53),'Oscura, central, clara y de bajo contraste. Etiquetas originales, pendientes de tu revisión visual.',font=FONT,fill='#555555')
    for c in range(3):
        choices=[r for r in refs['selection'] if r['class_id']==c]
        for j,r in enumerate(choices):
            x=20+j*355;y=95+c*330
            image=Image.open(r['image']).convert('RGB');bx,by,bw,bh=r['bbox'];pad=.18*max(bw,bh)
            crop=image.crop((max(0,int(bx-pad)),max(0,int(by-pad)),min(image.width,int(bx+bw+pad)),min(image.height,int(by+bh+pad))))
            tile(panel,crop,(x,y+35),(335,245));crop.save(out/f'real_c{c}_{j}.jpg',quality=96)
            draw.text((x,y),f'{CLASSES[c]} · {r["review_role"].split(";")[0]}',font=FONT,fill='#18372f')
            draw.text((x,y+286),f'fila {r["source_row"]} · {r["min_side_960"]:.0f} px a 960',font=SMALL,fill='#555555')
    panel.save(out/'referencias_reales.jpg',quality=95)
    panel=Image.new('RGB',(1440,1120),'#f2f1ec');draw=ImageDraw.Draw(panel)
    draw.text((24,16),'Materiales: referencia real / anterior / candidato',font=BOLD,fill='#18372f')
    draw.text((24,55),'Luz difusa idéntica en ambos renders. Hipótesis de clase; no validación de madurez del fruto.',font=FONT,fill='#555555')
    for c in range(3):
        y=90+c*335
        sources=[Image.open(out/f'real_c{c}_1.jpg').convert('RGB')]
        for bank in ['B','T']:
            path=attempt/f'focal_c{c}_diffuse_{bank}'/'rgb.png'
            image=Image.open(path).convert('RGB');mask=Image.open(path.parent/'mask_calyx_crisp_v2.png').convert('RGB')
            box=mask.getbbox();sources.append(image.crop(box) if box else image)
        for j,(source,label) in enumerate(zip(sources,['Real: etiqueta original','Material anterior','Material candidato'])):
            x=20+j*475;draw.text((x,y),f'{CLASSES[c]} · {label}',font=FONT,fill='#18372f');tile(panel,source,(x,y+35),(450,275))
    panel.save(out/'comparacion_clases.jpg',quality=96)
    for plant in range(4):
        panel=Image.new('RGB',(1440,760),'#f2f1ec');draw=ImageDraw.Draw(panel)
        draw.text((20,15),f'Planta nueva {plant+1} — misma geometría y cámara en cada fila',font=BOLD,fill='#18372f')
        for j,(bank,label) in enumerate(zip(BANKS,['Anterior','Solo luz','Solo materiales','Luz + materiales'])):
            x=10+j*360;draw.text((x,55),f'{bank}: {label}',font=FONT,fill='#18372f')
            for view in range(2):
                path=attempt/f'plant_{plant:02d}_view{view}_{bank}'/'rgb.png'
                tile(panel,Image.open(path).convert('RGB'),(x,90+view*325),(350,300))
        panel.save(out/f'encuadres_planta_{plant+1}.jpg',quality=95)
    if a.previous:
        previous=root/'calibration'/a.previous
        panel=Image.new('RGB',(1440,1420),'#f2f1ec');draw=ImageDraw.Draw(panel)
        draw.text((24,15),'Arquitectura: primera ronda / segunda ronda / segunda con nueva apariencia',font=BOLD,fill='#18372f')
        draw.text((24,52),'Mismas semillas. Cámara ajustada a cada planta completa; no implica igualdad de escala en píxeles.',font=FONT,fill='#555555')
        for plant in range(4):
            for j,(directory,bank,label) in enumerate([(previous,'B','Antes'),(attempt,'B','Ahora: apariencia anterior'),(attempt,'LT','Ahora: luz + materiales')]):
                x=15+j*475;y=90+plant*330
                draw.text((x,y),f'Planta {plant+1} · {label}',font=FONT,fill='#18372f')
                tile(panel,Image.open(directory/f'plant_{plant:02d}_view0_{bank}/rgb.png').convert('RGB'),(x,y+35),(450,280))
        panel.save(out/'estructura_antes_despues.jpg',quality=95)
    cards=''.join(f'<figure><img loading="lazy" src="../{html.escape(r["view_id"])}/rgb.png"><figcaption>{html.escape(r["view_id"])} · mediana objetivo {r["photometry"].get("target_luminance_median",0):.3f}</figcaption></figure>' for r in captures)
    document='''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Revisión del piloto de apariencia</title><style>body{font:16px system-ui;background:#f2f1ec;color:#18372f;margin:24px}main{max-width:1500px;margin:auto}h1{font-size:32px}.notice{background:#fff3c4;padding:18px;border-radius:12px}img{max-width:100%;height:auto}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:16px}figure{margin:0;background:white;padding:12px;border-radius:10px}figcaption{padding:8px 0;font-size:14px}</style><main><h1>Calibración de apariencia — revisión pendiente</h1><p class="notice">Esta galería no autoriza entrenamiento. Las clases describen apariencia del capacho. Conservamos los contactos geométricos pendientes en las auditorías; estas vistas son diagnósticas.</p><p>Revisar: correspondencia de cada clase; separación Madura/Sobremadura; luz sobre capacho y fondo; nervaduras, rugosidad y manchas. No hay recoloración de las referencias reales.</p><img src="referencias_reales.jpg"><img src="comparacion_clases.jpg">'''
    audits=[read(attempt/f'plant_{i:02d}_mesh_audit.json') for i in range(4)]
    collisions='/'.join(str(r['physical_collision_count']) for r in audits)
    document+=f'<p class="notice">Intersecciones físicas por planta: {collisions}. La galería es diagnóstica y no aprueba escenas para entrenamiento. El contexto mantiene malezas procedurales. Las clases candidatas siguen pendientes de revisión humana.</p>'
    if (attempt/'audit_review.json').exists():document+='<p><a href="../audit_review.json">Auditoría adicional y limitaciones de esta ronda</a></p>'
    document+='<h2>Ilustración aportada</h2><p>Referencia cualitativa. Su reproducción no convierte estos colores ni nuestras clases de capacho en una calibración normativa de madurez interna.</p><img src="ilustracion_aportada.webp">'
    document+=''.join(f'<img src="encuadres_planta_{i}.jpg">' for i in range(1,5))+'<h2>Las 50 capturas completas</h2><div class="grid">'+cards+'</div></main></html>'
    if a.previous:document=document.replace('<h2>Las 50 capturas completas</h2>','<h2>Cambio de arquitectura</h2><img src="estructura_antes_despues.jpg"><h2>Las 50 capturas completas</h2>')
    (out/'index.html').write_text(document,encoding='utf-8')
    write(out/'report_manifest.json',{'captures':len(captures),'files':{p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='report_manifest.json'},'profiles_sha256':sha(attempt/'profiles.json'),'human_review':'pending'})
    print(out/'index.html')


if __name__=='__main__':main()
