"""Publish static review sheets; preserve labels and all campaign locks."""
from pathlib import Path
from collections import Counter
import sys,math,textwrap,zipfile,shutil
from PIL import Image,ImageDraw,ImageFont
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'scripts'),str(REPO/'src')]
from appearance_campaign import read,write,sha,verify_sources
from daylight_augmentation_pilot import generation_paused
from uchuva_lsystem.dataset_completion import owner_alive
ROOT=REPO/'outputs/suspected_sobremadura_labels_20261113'


def main():
    current=REPO/'outputs/daylight_augmentation_115_20261112/pilot'
    generation_paused(current);training=verify_sources(current)
    processes=[]
    identities=[current/'controller_identity.json',*(current/'children').glob('*.json')]
    for p in identities:
        record=read(p)
        if 'pid' not in record:continue
        tick=record.get('creation_tick',record.get('created'))
        if tick is None:raise ValueError(f'Identity missing native creation tick: {p}')
        alive=owner_alive(dict(pid=record['pid'],creation_tick=str(tick)))
        if alive:raise ValueError(f'Pilot owner still active: {p}')
        processes.append(dict(path=str(p),pid=record['pid'],creation_tick=str(tick),alive=False))
    checked={}
    for p,h in read(ROOT/'input_lock.json')['files'].items():
        if sha(p)!=h:raise ValueError(f'Frozen input changed: {p}')
        checked[p]=h
    reviewed=read(ROOT/'reviewed_cases.json');selected=[c for c in reviewed['cases'] if c['priority']!='descartada_como_evidencia']
    assert len(selected)==17
    for prefix,title in [('P','Sospechas con etiqueta actual Pintona'),('M','Sospechas con etiqueta actual Madura'),('U','Posibles omisiones; clase y organo pendientes')]:
        cases=[c for c in selected if c['review_id'].startswith(prefix)]
        im=Image.new('RGB',(1500,1260),'#f5f2eb');draw=ImageDraw.Draw(im)
        font=ImageFont.truetype('arial.ttf',25);small=ImageFont.truetype('arial.ttf',19);heading=ImageFont.truetype('arial.ttf',30)
        draw.text((20,12),title,font=heading,fill='#173d37')
        draw.text((20,51),'Sospechas visuales de Codex. No son correcciones aprobadas ni un conteo de errores confirmados.',font=small,fill='#80562b')
        for n,c in enumerate(cases):
            x=(n%3)*500;y=90+(n//3)*555
            draw.text((x+10,y),f'{c["review_id"]} | fila {c["row"]} | '+(f'GT #{c["truth_index"]}' if c['truth_index'] is not None else 'sin caja'),font=font,fill='#173d37')
            image=Image.open(c['source_image']).convert('RGB');b=c['bbox'];pad=.15*max(b[2]-b[0],b[3]-b[1])
            crop=image.crop((max(0,math.floor(b[0]-pad)),max(0,math.floor(b[1]-pad)),min(image.width,math.ceil(b[2]+pad)),min(image.height,math.ceil(b[3]+pad))))
            scale=min(475/crop.width,425/crop.height);crop=crop.resize((round(crop.width*scale),round(crop.height*scale)),Image.Resampling.LANCZOS)
            im.paste(crop,(x+10+(475-crop.width)//2,y+38+(425-crop.height)//2))
            status=c['priority'].replace('_',' ')
            draw.text((x+10,y+470),status,font=small,fill='#80562b')
            note={'P1':'Oscuro y plegado','P2':'Pardo/gris y textura seca','P3':'Pigmentacion extensa y pliegues','P4':'Estrecho, seco; vista parcial','P5':'Pigmentado, aun inflado','P6':'Oscuro; poca resolucion',
                  'M1':'Pardo, alargado y plegado','M2':'Pardo, pliegues y apertura','M3':'Pardo/seco, detalle limitado','M4':'Pajizo con zona proximal oscura','M5':'Papeloso, todavia inflado','M6':'Gris/pardo, conserva volumen',
                  'U1':'Capacho oscuro, sin caja','U3':'Papeloso; confirmar organo','U4':'Pardo; capacho u hoja','U5':'Posible repeticion de U4','U6':'Contraluz; clase incierta'}[c['review_id']]
            draw.text((x+10,y+495),note,font=small,fill='#173d37')
        draw.text((20,1212),'Recortes limpios. Cada ficha individual incluye la foto completa y todas las etiquetas originales.',font=small,fill='#173d37')
        draw.text((20,1237),'Generacion y piloto pausados. RGB, etiquetas y pesos originales sin modificaciones.',font=small,fill='#173d37')
        im.save(ROOT/f'galeria_{prefix}.png')
    readme=['REVISION DE SOSPECHAS DE ETIQUETAS - 13/11/2026',
            '94 fotos reales de evaluacion cribadas visualmente; 144 regiones propuestas por modelos revisadas.',
            '17 casos documentados: 6 con etiqueta Pintona, 6 Madura y 5 posibles omisiones de instancia.',
            'No son 17 errores confirmados. U4/U5 pueden repetir el mismo organo. U6 no permite decidir clase.',
            'U2 se descarta como evidencia de omission: al ampliar parece tejido foliar.',
            'Sospechas de apariencia del capacho, no validacion de madurez interna ni reabsorcion del fruto.',
            'Los modelos solo propusieron regiones. Sus votos y confianzas no adjudican etiquetas.',
            'Test historicamente consultado: no cambiar labels para mejorar metricas ni reutilizar esta lista como ajuste del modelo.',
            'Las fichas tienen contexto a la izquierda con GT actual, recorte limpio a la derecha.',
            'Amarillo marca la region propuesta para revision, no es una nueva anotacion.',
            'No se realizaron nuevas inferencias, entrenamientos, renders o cambios de etiquetas.',
            '', 'INDICE']
    readme.extend(f'{c["review_id"]}: fila {c["row"]}, indice GT {c["truth_index"]}, {c["priority"]}: {c["visual_note"]}' for c in selected)
    (ROOT/'LEEME.txt').write_text('\n'.join(readme)+'\n',encoding='utf-8')
    write(ROOT/'selected_cases.json',dict(cases=selected,reviewer='Codex, human adjudication pending',confirmed_label_errors=None,labels_changed=False))
    zip_path=ROOT/'casos_sospechosos_para_revisar.zip'
    with zipfile.ZipFile(zip_path,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in [ROOT/'LEEME.txt',ROOT/'selected_cases.json',*(ROOT/f'galeria_{p}.png' for p in 'PMU'),*(Path(c['card']) for c in selected)]:z.write(p,p.relative_to(ROOT))
    with zipfile.ZipFile(zip_path) as z:
        assert z.testzip() is None and len(z.namelist())==22
    before=GALLERY_BEFORE=REPO/'outputs/sobremadura_four_models_20261113/graph_after.txt'
    shutil.copy2(before,ROOT/'graph_before.txt')
    def errors(p):
        raw=p.read_bytes();return [line for line in raw.decode('utf-16' if raw.startswith(b'\xff\xfe') else 'utf-8-sig').splitlines() if line]
    assert errors(before)==errors(ROOT/'graph_after.txt') and len(errors(before))==10
    state=dict(stage='visual_triage_complete_awaiting_human_adjudication',photos_screened=94,
               model_regions_screened=144,other_class_model_proposals=80,low_overlap_model_proposals=64,
               documented_candidates=17,current_labels=dict(Pintona=6,Madura=6,unannotated_region=5),
               priority_counts=dict(Counter(c['priority'] for c in selected)),confirmed_label_errors=None,
               generation_paused=True,pilot_paused=True,own_pilot_processes=processes,
               training_source_files_verified=len(training['files']),read_only_inputs_verified=len(checked),
               no_new_training=True,no_new_inference=True,no_new_plant_renders=True,labels_unchanged=True,
               exhaustive_object_audit=False,human_adjudication_pending=True,
               zip_integrity_verified=True,zip_files=22,graph_preexisting_errors=10,graph_new_errors=0)
    write(ROOT/'state.json',state)
    artifacts=[p for p in ROOT.rglob('*') if p.is_file() and p.name!='delivery_manifest.json']
    artifacts.extend([REPO/'docs/reports/sospechas_etiquetas_sobremadura_2026-11-13.md',REPO/'docs/repository_context_graph.json'])
    write(ROOT/'delivery_manifest.json',dict(verified_inputs=checked,artifacts={str(p):sha(p) for p in artifacts},
          scripts={str(REPO/'scripts'/p):sha(REPO/'scripts'/p) for p in ['prepare_sobremadura_label_review.py','render_suspected_label_cases.py','finalize_suspected_label_review.py']},state=state))
    print(state)


if __name__=='__main__':main()
