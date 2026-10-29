"""Collect independently admitted review scenes; never claim training results."""
from pathlib import Path
import argparse
import hashlib
import html
import json

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args();root=args.root.resolve();rows=[];cards=[]
    for path in sorted((root/'gallery').glob('*/admission.json')):
        record=json.loads(path.read_text(encoding='utf-8'));folder=path.parent
        after=next(r for r in record['audits'] if r['stage']=='after')
        if not (after['admitted'] and after['physical_crossings']==0 and after['ground_status']=='valid' and after['orientation']=='valid'):
            raise ValueError(f'Invalid admission presented as a final scene: {path}')
        if record['anatomy_before']!=record['anatomy_after']:raise ValueError('Changed protected anatomy')
        counts=record['anatomy_after']['counts'];image=folder/'after.png'
        if not image.is_file():raise FileNotFoundError(image)
        row=dict(scene=folder.name,counts=counts,crossings=0,clearance_warnings=after['positive_clearance_warnings'],
            ground='valid at 1 mm',orientation='valid',review='pending human visual review',
            anatomy_sha256=record['anatomy_after']['sha256'],image=str(image),image_sha256=sha(image),
            admission=str(path),admission_sha256=sha(path),scope=record['scope'])
        rows.append(row)
        relative=html.escape(folder.name)
        before=f'<a href="{relative}/before.png">Original, sin admisión</a> · ' if (folder/'before.png').is_file() else ''
        cards.append(f'''<article><h2>{relative}</h2><a href="{relative}/after.png"><img src="{relative}/after.png" alt="Arbusto corregido y auditado"></a>
<p><strong>0 cruces auditados</strong> · suelo 1 mm · {counts['leaves']} hojas · {counts['fruits']} frutos · {counts['calyces']} capachos.</p>
<p>{row['clearance_warnings']} advertencias de proximidad positiva. Cantidades totales del árbol, no conteos de órganos visibles.</p>
<p>{before}<a href="{relative}/admission.json">Auditorías y hashes</a> · <a href="{relative}/scene.blend">Escena Blender</a></p></article>''')
    manifest=dict(status='physical_review_ready_pending_human_visual_review' if rows else 'no_admitted_scenes',
        training_started=False,scenes=rows,unique_morphologies=len({r['anatomy_sha256'] for r in rows}),
        scope='Small diagnostic review; not a training bank or proof of botanical validity; failed attempts preserved')
    (root/'review_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    page='''<!doctype html><html lang="es"><meta charset="utf-8"><title>Revisión nodal de uchuva</title>
<style>body{font:17px/1.5 system-ui;max-width:1100px;margin:30px auto;padding:0 20px;background:#f5f4ef;color:#203225}h1,h2{line-height:1.2}article{background:white;padding:20px;margin:24px 0;border-radius:12px}img{width:100%;height:auto}a{color:#245b45}.notice{padding:16px;border-left:4px solid #a67c21;background:#fff8dd}</style>
<h1>Uchuva: corrección nodal y revisión física</h1><p>Sin entrenamiento. Revisión visual humana pendiente.</p>
<p class="notice">Se reconstruyó cada árbol desde JSON. La admisión exige cero cruces de las mallas auditadas, suelo válido a 1 mm y unión/orientación de capachos verificadas. Se mantienen advertencias de proximidad y la excepción hoja–hoja. Flores y contexto no tienen certificación exhaustiva. El suelo plano es diagnóstico.</p>
<p>Se conservan órganos, dimensiones nominales, estados e identidades. La cámara del antes/después es la misma. Las tres clases son apariencia del capacho; no madurez agronómica real.</p>'''+''.join(cards)+ '<p>Los intentos rechazados permanecen en el directorio de revisión y no forman parte de esta galería de escenas admitidas.</p></html>'
    (root/'gallery/index.html').write_text(page,encoding='utf-8')
    print(json.dumps(dict(admitted_scenes=len(rows),unique_morphologies=manifest['unique_morphologies'],training_started=False)))

if __name__=='__main__':main()
