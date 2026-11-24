"""Train-only domain-gap diagnostics and gallery before detector selection."""
from __future__ import annotations
import argparse
from collections import Counter
import html
from pathlib import Path
import sys
import numpy as np
from PIL import Image,ImageDraw,ImageOps

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from appearance_campaign import read,write,sha,verify_bank,BANKS,NAMES


def summary(values):
    values=[float(v) for v in values if v is not None and np.isfinite(v)]
    return dict(n=len(values),p10=float(np.quantile(values,.1)),median=float(np.median(values)),
                p90=float(np.quantile(values,.9))) if values else dict(n=0,p10=None,median=None,p90=None)


def photometry(pixels):
    if not len(pixels):return dict(luminance_median=None,saturation_median=None,contrast=None)
    rgb=pixels.astype(float)/255
    lum=rgb@np.array([.2126,.7152,.0722])
    sat=(rgb.max(1)-rgb.min(1))/np.maximum(rgb.max(1),1e-6)
    return dict(luminance_median=float(np.median(lum)),saturation_median=float(np.median(sat)),contrast=float(np.std(lum)))


def report(root):
    root=Path(root).resolve();views=verify_bank(root)
    refs=read(root/'references/real_instances.json');assert refs['source_split']=='train' and not refs['test_images_read']
    out=root/'banks/diagnostics';out.mkdir(exist_ok=True)
    records=[];contexts={b:[] for b in BANKS}
    for view in views:
        exemplar=view['variants']['B'];annotation=read(Path(exemplar['mask']).parent/'annotations.json')
        im=Image.open(exemplar['mask']).convert('RGB');ratio=min(1,640/max(im.size));size=tuple(max(1,round(v*ratio)) for v in im.size)
        mask=np.asarray(im.resize(size,Image.Resampling.NEAREST)).astype(np.int32)
        codes=(mask[:,:,0]*65536+mask[:,:,1]*256+mask[:,:,2]).ravel()
        order=np.argsort(codes);sorted_codes=codes[order]
        groups=[]
        for instance in view['instances']:
            color=annotation['palette'][str(instance['mask_id'])];code=color[0]*65536+color[1]*256+color[2]
            a,b=np.searchsorted(sorted_codes,[code,code+1]);groups.append((instance,order[a:b]))
        for bank in BANKS:
            row=view['variants'][bank]
            rgb=np.asarray(Image.open(row['image']).convert('RGB').resize(size,Image.Resampling.LANCZOS)).reshape(-1,3)
            contexts[bank].append(photometry(rgb[codes==0]))
            for instance,indices in groups:
                records.append(dict(bank=bank,view_id=view['view_id'],scene_id=view['scene_id'],
                    class_id=instance['class_id'],min_side_960=instance['min_side_960'],
                    measurement='visible synthetic mask, longest side <=640, encoded sRGB; no reflectance',
                    **photometry(rgb[indices])))
    real_density=Counter(r['source_row'] for r in refs['instances'])
    # Included training images with no calyx count as zero, not an omitted image.
    train=read(root/'real_manifest.json');raw=train.get('records',train.get('rows'))
    real_density_values=[real_density[r['source_row']] for r in raw if r['split']=='train' and r.get('status','included')=='included']
    banks={};real={};warnings=[]
    for c in range(3):
        subset=[r for r in refs['instances'] if r['class_id']==c]
        real[str(c)]={k:summary(r[k] for r in subset) for k in ('min_side_960','luminance_median','saturation_median','contrast')}
        real[str(c)]['frequency']=len(subset)/len(refs['instances'])
    for bank in BANKS:
        subset=[r for r in records if r['bank']==bank];classes={}
        for c in range(3):
            items=[r for r in subset if r['class_id']==c]
            classes[str(c)]={k:summary(r[k] for r in items) for k in ('min_side_960','luminance_median','saturation_median','contrast')}
            classes[str(c)]['frequency']=len(items)/max(1,len(subset))
            ratio=classes[str(c)]['min_side_960']['median']/real[str(c)]['min_side_960']['median'] if items else None
            delta=classes[str(c)]['frequency']-real[str(c)]['frequency']
            if ratio is not None and not .8<=ratio<=1.2:warnings.append(dict(bank=bank,class_id=c,kind='median_size_ratio',value=ratio))
            if abs(delta)>.05:warnings.append(dict(bank=bank,class_id=c,kind='class_frequency_delta',value=delta))
            for key in ('luminance_median','saturation_median'):
                a=classes[str(c)][key]['median'];b=real[str(c)][key]['median']
                if a is not None and b is not None and abs(a-b)>.1:warnings.append(dict(bank=bank,class_id=c,kind=key+'_delta',value=a-b))
        banks[bank]=dict(classes=classes,images=len(views),instances=len(subset),
            density=summary(len(v['instances']) for v in views),
            tiny_fraction=sum(r['min_side_960']<16 for r in subset)/max(1,len(subset)),
            context={k:summary(r[k] for r in contexts[bank]) for k in ('luminance_median','saturation_median','contrast')})
    backgrounds=refs['backgrounds']
    payload=dict(reference_split='train',used_validation=False,used_test=False,views=len(views),
        real=dict(classes=real,density=summary(real_density_values),
                  context={k:summary(r.get(k) for r in backgrounds) for k in ('luminance_median','saturation_median','contrast')}),
        banks=banks,engineering_review_flags=warnings,
        flag_policy='Descriptive: median size outside +/-20%, class frequency beyond 5pp, encoded luma/saturation beyond .1. Not significance tests or admission gates.',
        limitations=['Real references use human polygons when available and flagged boxes otherwise; synthetic uses exact visible masks. Small masks can disappear at 640.',
            'Encoded camera RGB and rendered RGB do not measure calibrated reflectance or illumination.',
            'Procedural sky/ground and limited support geometry remain simpler than real field backgrounds.',
            '24 target plants and 12 scenes are broader than four plants, but do not represent independent farms or sessions.',
            'All banks share foliage diversity, architecture and class allocation; their separate contributions cannot be inferred from this factorial.'])
    write(out/'domain_gap.json',payload)
    write(out/'instance_measurements.json',dict(rows=records))
    samples=[]
    for scene in sorted({v['scene_id'] for v in views}):
        view=next(v for v in views if v['scene_id']==scene)
        sheet=Image.new('RGB',(1600,480),'#f3f2ed');draw=ImageDraw.Draw(sheet)
        for i,bank in enumerate(BANKS):
            im=Image.open(view['variants'][bank]['image']).convert('RGB');im=ImageOps.contain(im,(390,440))
            sheet.paste(im,(i*400+(390-im.width)//2,30+(440-im.height)//2));draw.text((i*400+12,8),f'{scene} | {bank}',fill='#18372f')
        p=out/(scene+'_four_banks.jpg');sheet.save(p,quality=95);samples.append(p)
    lines=['# Banco sintético heterogéneo: diferencias antes de entrenar','',
        'Referencias exclusivamente de entrenamiento; estas medidas no usan validación ni prueba.','',
        '| Banco | Imágenes | Instancias | Mediana de instancias/imagen | Fracción <16 px |', '|---|---:|---:|---:|---:|']
    for b,r in banks.items():lines.append(f"| {b} | {r['images']} | {r['instances']} | {r['density']['median']:.1f} | {100*r['tiny_fraction']:.1f}% |")
    lines+=['',f"Mediana real: {payload['real']['density']['median']:.1f} instancias/imagen.",'',
        '## Diferencias por clase','', '| Banco | Clase | Tamaño mediano sintético / real (px a 960) | Frecuencia sintética / real | Brillo codificado sintético / real |', '|---|---|---:|---:|---:|']
    for b in BANKS:
        for c in range(3):
            a=banks[b]['classes'][str(c)];r=real[str(c)]
            lines.append(f"| {b} | {NAMES[c]} | {a['min_side_960']['median']} / {r['min_side_960']['median']} | {100*a['frequency']:.1f}% / {100*r['frequency']:.1f}% | {a['luminance_median']['median']} / {r['luminance_median']['median']} |")
    lines+=['','## Cómo sopesar las diferencias','',
        'Se mantienen las dosis anidadas 46/115/230, sin exigir equivalencia geométrica. Una dosis menor reduce la exposición a diferencias de dominio; la elección usará AP macro de validación y se contrastará contra real, B y repetición. Se reportará también Madura: subir el promedio a costa de esta clase es un intercambio.',
        'La proporción de imágenes no expresa la exposición por instancias. Si los sintéticos contienen más objetos, se documentará la exposición efectiva. Limitar el peso de pérdida por imagen o por dominio podría estudiarse después mediante una ablación; no se introduce ahora un cambio de entrenador.',
        'Fondos más simples pueden producir atajos. El tutorado y la maleza varían por escena y se mantienen dentro de cada cuarteto. Agregar más texturas/fondos reales o HDRI y variación de captura es una hipótesis futura; el presente factorial mide luz/materiales en ese contexto común.',
        'Los colores de las clases conservan incertidumbre de apariencia y no validan madurez interna. Si una clase mantiene una brecha grande de color, conviene calibrarla con referencias anotadas y evaluar su efecto por separado antes de aumentar su dosis.','',
        '## Límites','']+['- '+s for s in payload['limitations']]
    for p in samples:lines+=['',f'![{p.stem}]({p.name})']
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Banco heterogéneo</title><style>body{font:18px system-ui;max-width:1600px;margin:24px auto;background:#f3f2ed;color:#18372f}img{max-width:100%}</style><h1>Banco heterogéneo: B / L / T / LT</h1><p>Referencias de entrenamiento. Diferencias descriptivas; resultados del detector pendientes.</p><p><a href="report.md">Diagnóstico y recomendaciones</a> · <a href="domain_gap.json">Mediciones</a></p>'+''.join('<img loading="lazy" src="'+html.escape(p.name)+'">' for p in samples),encoding='utf-8')
    write(out/'manifest.json',dict(files={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='manifest.json'},bank_sha256=sha(root/'banks/manifest.json'),selection_used_test=False))
    return payload


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    print(report(a.root)['views'])
