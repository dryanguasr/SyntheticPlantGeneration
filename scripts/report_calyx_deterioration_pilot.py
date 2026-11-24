"""Compose visual-review plates and preserve the paused-bank boundary."""
from pathlib import Path
import sys,shutil,time,html
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts')]
from appearance_campaign import read,write,sha,require
from uchuva_lsystem.dataset_completion import verify_sources,owner_alive,baseline_rows,new_rows
from PIL import Image,ImageDraw,ImageFont


def report(out):
    plan=read(out/'plan.json');result=read(out/'result.json');source=Path(plan['source_campaign'])
    require(result['completed'],'Render incomplete')
    require(not owner_alive(read(out/'process.json')),'Pilot owner still running')
    require(read(source/'pause_requested.json')['active'],'Bank must remain paused')
    pre=read(out/'preservation.json')
    require(sha(source/'budget.json')==pre['generation_budget_sha256'],'Bank budget changed')
    require(sha(source/'source_lock.json')==pre['source_lock_sha256'],'Historical source lock changed')
    require(sha(source/'dataset/pool_lock.json')==pre['pool_lock_sha256'],'Pool lock changed')
    for path,h in pre['plants'].items():require(sha(path)==h,'Admitted plant modified')
    verify_sources(source)
    require(len(baseline_rows(source)+new_rows(source))==503,'Bank image inventory changed')
    for p,h in read(out/'source_lock.json')['files'].items():require(sha(p)==h,'Pilot source changed')
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',26)
    small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',21)
    board=Image.new('RGB',(1600,1080),'#f3f0e9');draw=ImageDraw.Draw(board)
    draw.text((800,20),'Madura y grados de deterioro visible del capacho',fill='#1d2926',font=font,anchor='mt')
    for i,stage in enumerate(plan['stages']):draw.text((160+i*320,77),stage['label'],fill='#1d2926',font=small,anchor='mt')
    for index,variant in enumerate(('Pardo y oscurecimiento proximal','Secado más claro y decoloración')):
        record=next(r for r in result['records'] if r['specimen']==index and r['lighting']=='field')
        require(sha(record['image'])==record['image_sha256'],'Raw render changed')
        with Image.open(record['image']) as im:crop=im.convert('RGB').crop((0,140,1600,500))
        top=130+index*455;board.paste(crop,(0,top))
        draw.text((800,top+373),variant+' · misma cámara y escala en todas las columnas',fill='#273b32',font=small,anchor='mt')
    draw.text((800,1050),'Piloto visual de órganos aislados. Grados heurísticos; no nuevas clases ni plantas admitidas.',fill='#273b32',font=small,anchor='mt')
    board.save(out/'comparison_plate.png')
    diffuse=Image.new('RGB',(1600,1080),'#f3f0e9');diffuse_draw=ImageDraw.Draw(diffuse)
    diffuse_draw.text((800,20),'Mismos capachos con luz más difusa',fill='#1d2926',font=font,anchor='mt')
    for i,stage in enumerate(plan['stages']):diffuse_draw.text((160+i*320,77),stage['label'],fill='#1d2926',font=small,anchor='mt')
    for index in range(2):
        r=next(r for r in result['records'] if r['specimen']==index and r['lighting']=='diffuse')
        with Image.open(r['image']) as im:diffuse.paste(im.convert('RGB').crop((0,140,1600,500)),(0,130+index*455))
    diffuse.save(out/'diffuse_plate.png')
    snapshots=out/'source_snapshot';snapshots.mkdir(exist_ok=True)
    for name in ('calyx_deterioration.py','blender_calyx_deterioration.py'):
        shutil.copy2(REPO/'src/uchuva_lsystem'/name,snapshots/name)
    for name in ('render_calyx_deterioration_pilot.py','prepare_calyx_deterioration_pilot.py','report_calyx_deterioration_pilot.py'):
        shutil.copy2(REPO/'scripts'/name,snapshots/name)
    write(source/'future_calyx_revision.json',dict(status='visual_pilot_pending_user_review',pilot=str(out),
        instruction='Keep existing overmature appearances valid. Future new overmature calyces should span texture/color changes, optional proximal darkening, progressive drying/compression and size loss.',
        calyx_classes_unchanged=True,not_all_overmature_must_be_black=True,apply_to_existing_admitted_trees=False,
        bank_remains_paused=True,internal_fruit_compatibility_requires_validation=True,
        physiological_resorption='not established by this visual pilot'))
    doc=REPO/'docs/reports/piloto_deterioro_capachos_2026-10-31.md'
    lines=['# Piloto visual de secado y deterioro del capacho','',
        'Se generaron cuatro láminas Blender: dos ejemplares derivados de unidades del modelo morfológico '
        'y cinco estados por ejemplar, bajo dos luces. Son **órganos aislados para revisión visual**, '
        'no nuevas plantas admitidas ni nuevas imágenes del banco de entrenamiento.',
        '', '## Observación y representación','',
        'El usuario observó cambios de textura, tonos marrones, oscurecimiento próximo al pedicelo, '
        'pérdida de color/tamaño y compresión progresiva en parte de los capachos etiquetados Sobremadura. '
        'Se conserva la validez de la apariencia pajiza existente: deterioro visible y clase no son '
        'equivalencias obligatorias. No se añaden clases ni se reetiqueta el banco actual.',
        '', 'La secuencia compara Madura, Sobre pajiza actual y deterioro leve/intermedio/avanzado. '
        'La segunda variante aumenta la decoloración y reduce el ennegrecimiento para evitar que negro '
        'sea una condición universal de la clase. Se mantienen semilla de malla, cámara y escala '
        'dentro de cada ejemplar; cambian explícitamente las hipótesis de superficie/forma.',
        '', '## Implementación','',
        '- `calyx_deterioration.py`: estado puro, serializable y determinista. Los valores numéricos '
        'son `engineering_heuristic_pending_visual_review`; no edades ni medidas botánicas.',
        '- `blender_calyx_deterioration.py`: interpreta esa hipótesis sobre una copia de la malla '
        'y del material; manchas marrones irregulares, oscurecimiento proximal, decoloración, '
        'rugosidad y pliegues. Mantiene el polo de unión al pedicelo. No modifica el intérprete histórico.',
        '- La forma se comprime asimétricamente, con pliegues locales y torsión suave; no es sólo '
        'un escalado uniforme. La apariencia anterior se conserva como columna de control.',
        '', '![Comparación principal](../../outputs/calyx_deterioration_pilot_20261031/revisions/phenotype_variation_02/comparison_plate.png)',
        '', '## Alcance y comprobaciones','',
        'Las cuatro pruebas puras pasaron: determinismo, identidad sin deterioro, conservación del '
        'polo proximal, compresión y variación sin ennegrecimiento obligatorio. En Blender se '
        'comprobó ausencia de aristas no manifold y error de unión inferior a1e−6cm en los diez '
        'estados geométricos. Esto **no certifica** ausencia de toda autointersección ni sustituye '
        'la auditoría de una planta completa.',
        '', 'La lámina muestra sólo el cáliz y su pedicelo de referencia. No se instancia el fruto '
        'interior: la compatibilidad de una envoltura comprimida con el tamaño/estado del fruto '
        'necesita un modelo explícito y nueva auditoría antes de aplicar la variante a escenas '
        'admitidas. No se simula ni se valida reabsorción fisiológica ni se atribuye todo '
        'oscurecimiento a envejecimiento normal.',
        '', 'El estudio de de Souza et al.2022 distingue propiedades de cáliz y fruto de Physalis '
        'y sus relaciones con pérdida de agua, pero no calibra esta secuencia ni demuestra el '
        'mecanismo de reabsorción propuesto. Referencia consultada: '
        '[Multifunctional Contribution of the Inflated Fruiting Calyx](https://doi.org/10.3389/fpls.2022.888930). '
        'No se usaron imágenes de publicaciones como texturas ni fondos.',
        '', '## Preservación y revisión','',
        'La revisión inicial y la de pliegues permanecen archivadas; la vigente es '
        '`revisions/phenotype_variation_02`, con fuentes/hashes, planos JSON, cuatro RGB y escena Blender. '
        'Se inspeccionaron las láminas; no se afirma fotorealismo ni mejora del detector. '
        'El banco continúa con503 imágenes y20 árboles originales intactos, con presupuesto y lock '
        'históricos sin cambios. No hubo entrenamiento ni reanudación de la campaña.',
        '', 'La instrucción para próximas variantes queda en `future_calyx_revision.json`, sin '
        'liberar la pausa ni modificar escenas actuales. El siguiente paso depende de revisar '
        'esta propuesta visual; no se admiten automáticamente estas formas como plantas válidas.']
    doc.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    page='<html lang="es"><meta charset="utf-8"><title>Maduras y deterioro del capacho</title><style>body{font:18px system-ui;max-width:1650px;margin:auto;padding:20px}img{max-width:100%}</style><h1>Piloto de deterioro visible</h1><p>Madura, Sobre pajiza existente, leve, intermedia y avanzada. Misma escala; dos variantes. Revisión visual pendiente del usuario; banco pausado, sin entrenamiento.</p><img src="comparison_plate.png"><h2>Luz difusa</h2><img src="diffuse_plate.png"><h2>Renders originales</h2>'
    for r in result['records']:page+=f'<p><a href="{Path(r["image"]).name}">{r["specimen"]} · {r["lighting"]}</a></p>'
    (out/'review.html').write_text(page+'</html>',encoding='utf-8')
    graphpath=REPO/'docs/repository_context_graph.json';shutil.copy2(graphpath,out/'graph_before.json');graph=read(graphpath)
    graph['nodes'].append(dict(id='entrypoint.calyx_deterioration_visual_pilot',type='entrypoint',label='Piloto opt-in de deterioro visible del capacho',
        summary='Estado puro determinista y superficies/forma interpretadas en Blender sobre copias: control Madura, Sobre pajiza valida y tres grados de deterioro; variante oscura proximal y variante decolorada. Parametros heurísticos basados en observacion del usuario; no simula reabsorcion ni madurez interna. Cuatro vistas de organos aislados, no plantas admitidas; fruto interior y contactos completos pendientes. Preserva503 vistas/20 arboles y fuentes historicas, banco pausado y sin entrenamiento.',
        paths=['src/uchuva_lsystem/calyx_deterioration.py','src/uchuva_lsystem/blender_calyx_deterioration.py','scripts/prepare_calyx_deterioration_pilot.py','scripts/render_calyx_deterioration_pilot.py','scripts/report_calyx_deterioration_pilot.py','tests/test_calyx_deterioration.py',str(doc.relative_to(REPO)).replace('\\','/')],
        evidence=[dict(path='src/uchuva_lsystem/calyx_deterioration.py',locator='class CalyxDeterioration:'),dict(path='src/uchuva_lsystem/blender_calyx_deterioration.py',locator='def apply_shell_state('),dict(path='tests/test_calyx_deterioration.py',locator='def test_deterioration_is_not_always_black(')]))
    graph['edges'].append(dict(source='entrypoint.calyx_deterioration_visual_pilot',target='entrypoint.sobremadura_error_diagnosis',relation='proposes_visual_coverage_hypothesis_without_relabeling_or_training',evidence=[dict(path=str(doc.relative_to(REPO)).replace('\\','/'),locator='## Observación y representación')]))
    write(graphpath,graph)
    files=[doc,graphpath,out/'plan.json',out/'result.json',out/'source_lock.json',out/'comparison_plate.png',out/'diffuse_plate.png',out/'review.html',Path(__file__)]
    write(out/'review_completion.json',dict(completed=True,reviewer='Codex',human_visual_review='pending',
        preserved_bank_images=503,preserved_admitted_plants=20,training_started=False,bank_generation_paused=True,
        scope='visual organ fixtures only, not certified new plants',artifacts={str(p):sha(p) for p in files},finished_utc=time.time()))
    write(out.parents[1]/'latest_revision.json',dict(revision=str(out),review=str(out/'review.html'),report=str(doc),status='awaiting_user_visual_review'))
    print('Review plates and report complete; existing bank unchanged and paused')


if __name__=='__main__':report(Path(sys.argv[1]).resolve())
