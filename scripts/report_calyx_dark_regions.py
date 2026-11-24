"""Review train-only darkness screening without changing labels or generator."""
from pathlib import Path
from collections import Counter,defaultdict
import argparse,math,time,shutil
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from appearance_campaign import read,write,sha,require,NAMES,verify_sources
from quantify_calyx_dark_regions import describe,darkness_metrics


def run(out):
    import cv2
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    root=out.parents[0];repo=Path(__file__).resolve().parents[1]
    data=read(out/'measurements.json');raw=read(out/'summary.json');targets=[r for r in data if r['class_id']==2]
    reviewed=read(out/'review_selection.json')['ids']
    issues={
        'row_0336_box_004':'Foreground separation ambiguous between overlapping calyces; exclude approximate surface statistic conservatively',
        'row_0490_box_008':'Leaf occludes central calyx and is included by approximate foreground',
        'row_0490_box_001':'Approximate mask isolates dark sector rather than complete visible husk',
        'row_0562_box_004':'Foreground leaf overlaps calyx boundary and mask',
        'row_0136_box_006':'Green occluding leaf enters approximate foreground',
        'row_0577_box_006':'Occluding dark leaf dominates approximate mask; not evidence of near-total dark calyx'}
    excluded={r['id'] for r in targets if r['flags']}|set(issues)
    retained=[r for r in targets if r['id'] not in excluded and r['approximate_surface']]
    qc={str(t):describe(r['approximate_surface']['absolute_dark_fraction'][str(t)] for r in retained) for t in (25,35,45)}
    # One visibly connected pedicel cue, estimated by Codex, not a population orientation label.
    example=next(r for r in targets if r['id']=='row_0297_box_000')
    with Image.open(Path(example['folder'])/'crop.png') as im:rgb=np.asarray(im.convert('RGB'))
    h,w=example['work_shape'][:2];rgb=cv2.resize(rgb,(w,h),interpolation=cv2.INTER_AREA)
    mask=np.asarray(Image.open(Path(example['folder'])/'approximate_mask.png'))>0
    yy,xx=np.nonzero(mask);center=np.array([xx.mean(),yy.mean()]);neck=np.array([.42*w,.115*h])
    axis=(neck-center)/np.linalg.norm(neck-center);yygrid,xxgrid=np.indices(mask.shape)
    def zones(angle):
        a=math.radians(angle);direction=np.array([axis[0]*math.cos(a)-axis[1]*math.sin(a),axis[0]*math.sin(a)+axis[1]*math.cos(a)])
        proj=(xxgrid-center[0])*direction[0]+(yygrid-center[1])*direction[1];vals=proj[mask]
        near=mask&(proj>=vals.min()+.70*(vals.max()-vals.min()))
        return near,mask&~near
    proximal,rest=zones(0)
    axial=dict(id=example['id'],neck_point_fraction=[.42,.115],orientation_provenance='Codex visual estimate of visible pedicel connection; not human anatomical annotation',
        zone_definition='proximal30% of approximate mask projected span toward pedicel estimate',
        proximal=darkness_metrics(rgb,proximal),remaining=darkness_metrics(rgb,rest),
        proximal_dark35_rotation_sensitivity=[darkness_metrics(rgb,zones(a)[0])['absolute_dark_fraction']['35'] for a in (-15,0,15)])
    write(out/'reviewed_summary.json',dict(raw_summary_sha256=sha(out/'summary.json'),
        automatic_Sobremadura_count=363,reviewed_contact_sheet_objects=len(reviewed),
        visual_review='Codex, screening only; not manual ground-truth masks',visual_issues=issues,
        excluded_approximate_masks=sorted(excluded),remaining_provisional_masks=len(retained),provisional_sensitivity_after_exclusions=qc,
        axial_example=axial,no_anatomical_orientation_assumed_for_population=True))
    # Quantification plot: each object has equal weight; no claim of independence.
    fig,axes=plt.subplots(1,2,figsize=(12,4.2));colors=['#518f64','#b99035','#76558a']
    for index,(name,color) in enumerate(zip(NAMES,colors)):
        s=raw['classes'][name]['approximate_surface']['35'];axes[0].errorbar(index,s['median']*100,
            yerr=np.array([[s['median']-s['q25']],[s['q75']-s['median']]])*100,fmt='o',color=color,capsize=7)
    axes[0].set(xticks=[0,1,2],xticklabels=['Pintona\n116 controles','Madura\n81 controles','Sobremadura\n363 cajas'],
        ylabel='Área oscura aproximada (%)',title='L*<35: mediana y rango intercuartil')
    for t,color in ((35,'#6b5087'),(45,'#b59146')):
        values=sorted(r['approximate_surface']['absolute_dark_fraction'][str(t)]*100 for r in targets)
        axes[1].plot(values,np.arange(1,len(values)+1)/len(values),label=f'L*<{t}',color=color)
    axes[1].set(xlabel='Área oscura aproximada (%)',ylabel='Fracción acumulada de cajas Sobremadura',title='Sensibilidad al criterio de oscuridad');axes[1].legend()
    fig.tight_layout();fig.savefig(out/'coverage_summary.png',dpi=160);plt.close(fig)
    ids=['row_0626_box_002','row_0658_box_002','row_0297_box_000','row_0358_box_000','row_0096_box_001','row_0438_box_000']
    sheet=Image.new('RGB',(1800,1100),'#f2f0e8');draw=ImageDraw.Draw(sheet)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',23);small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',19)
    draw.text((900,15),'Sobremaduras reales de train · superficie visible aproximada',fill='black',font=font,anchor='mt')
    draw.text((900,48),'Verde: máscara estimada · magenta: píxeles L*<35. Oscuridad fotografiada, no lesión certificada.',fill='black',font=small,anchor='mt')
    for i,identifier in enumerate(ids):
        r=next(r for r in targets if r['id']==identifier);x=(i%3)*600;y=95+(i//3)*485
        with Image.open(Path(r['folder'])/'crop.png') as im:
            original=im.convert('RGB');h,w=r['work_shape'][:2];rgb=cv2.resize(np.asarray(original),(w,h),interpolation=cv2.INTER_AREA)
        mask=np.asarray(Image.open(Path(r['folder'])/'approximate_mask.png'))>0
        light=cv2.cvtColor(rgb.astype(np.float32)/255,cv2.COLOR_RGB2Lab)[:,:,0];overlay=rgb.copy();dark=mask&(light<35)
        overlay[dark]=(.6*overlay[dark]+.4*np.array([220,0,200])).astype(np.uint8)
        cv2.drawContours(overlay,cv2.findContours(mask.astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0],-1,(0,255,80),1)
        for j,im in enumerate((original,Image.fromarray(overlay))):
            im.thumbnail((285,350));sheet.paste(im,(x+j*300+(285-im.width)//2,y+70+(350-im.height)//2))
        a=r['approximate_surface']['absolute_dark_fraction']
        draw.text((x+10,y),identifier,fill='black',font=font)
        draw.text((x+10,y+31),f"L*<35: {a['35']:.0%} · L*<45: {a['45']:.0%}",fill='black',font=small)
        if identifier=='row_0438_box_000':draw.text((x+10,y+430),'Oscuridad global/sombra posible; no probar lesión',fill='#7c4325',font=small)
    sheet.save(out/'examples_quantified.png')
    fig,axes=plt.subplots(1,2,figsize=(9,4.5));axes[0].imshow(rgb if False else np.asarray(Image.open(Path(example['folder'])/'crop.png')));axes[0].axis('off');axes[0].set_title('Ejemplo de unión proximal estimada')
    with Image.open(Path(example['folder'])/'crop.png') as im:ex=cv2.resize(np.asarray(im.convert('RGB')),(example['work_shape'][1],example['work_shape'][0]),interpolation=cv2.INTER_AREA)
    visual=ex.copy();visual[proximal]=(.5*visual[proximal]+.5*np.array([40,150,255])).astype(np.uint8)
    axes[1].imshow(visual);axes[1].plot(neck[0],neck[1],'r+');axes[1].axis('off')
    axes[1].set_title(f"Zona proximal estimada: {axial['proximal']['absolute_dark_fraction']['35']:.0%} oscura\nResto: {axial['remaining']['absolute_dark_fraction']['35']:.0%}")
    fig.tight_layout();fig.savefig(out/'proximal_example.png',dpi=150);plt.close(fig)
    doc=repo/'docs/reports/cuantificacion_oscuridad_capachos_train_2026-10-31.md'
    s=raw['classes']['Sobremadura'];p=s['approximate_surface']
    lines=['# Cuantificación exploratoria de regiones oscuras en capachos de train','',
        '**Se midió oscuridad fotografiada, no pigmentación intrínseca ni necrosis.** Se usaron exclusivamente '
        'las363 anotaciones Sobremadura en170 imágenes de train, de siete grupos. No se leyeron píxeles '
        'ni labels de val/test. Hay116 controles Pintona y81 Madura escogidos en las mismas fotos, '
        'por proximidad/tamaño a un objetivo Sobremadura de referencia. No representan todos los ejemplares '
        'de esas clases ni son objetos biológicamente independientes.',
        '', '## Qué se midió','',
        'Se convierte RGB de los JPEG a L* perceptual0–100 sin calibración de cámara. Tres límites '
        'compartidos,25/35/45, describen oscuridad estricta a más amplia; no son umbrales botánicos '
        'ni fueron optimizados para clasificar. La fracción es número de píxeles bajo el límite '
        'dividido por el área analizada. Se calculan dos denominadores: elipse central geométrica '
        'de60% del ancho/70% del alto de la caja, y máscara automática aproximada de superficie visible.',
        '', 'La máscara usa GrabCut con fondo fuera de caja y una pequeña semilla central, a resolución '
        'máxima224px. Puede perder tejido oscuro o incluir hojas/vecinos. '
        '[La documentación de OpenCV](https://docs.opencv.org/4.x/d8/d83/tutorial_py_grabcut.html) '
        'advierte que se necesitan correcciones cuando la separación falla. No se presenta ninguna '
        'de estas máscaras como ground truth. Los porcentajes se conservan separados de las etiquetas.',
        '', '## Resultados de Sobremadura','',
        '| Criterio L* | Mediana del área en máscara aproximada | Q25–Q75 | Mediana en región central |','|---|---:|---:|---:|']
    for t in ('25','35','45'):
        a=p[t];lines.append(f"| <{t} | {a['median']*100:.1f}% | {a['q25']*100:.1f}–{a['q75']*100:.1f}% | {s['core'][t]['median']*100:.1f}% |")
    lines+=['', 'Con L*<35, el90% de cajas queda por debajo de35,8% de área oscura estimada. '
        'Con L*<45 ese percentil sube a70,1%. Hay180 casos en0–5%,101 en5–20%,67 en20–50%, '
        '11 en50–80% y4 candidatos en≥80% usando las máscaras crudas a L*<35. A L*<45 aparecen '
        '20 candidatos≥80%. La dependencia del umbral y de la máscara impide llamar a esos '
        'conteos prevalencia de manchas o deterioro.',
        '', 'Se inspeccionaron30 casos estratificados por oscuridad. Dos de los cuatro candidatos '
        '≥80% a L*<35 son claramente problemáticos: una máscara minúscula de161px '
        '(`row_0358_box_001`) y una hoja oclusora incluida (`row_0577_box_006`). '
        'Los otros candidatos tampoco prueban pigmentación: la sombra puede oscurecer casi '
        'todo el órgano. Los fallos observados se conservan, no se corrigen modificando labels.',
        '', f"Como sensibilidad conservadora se excluyeron{len(excluded)} máscaras con alertas automáticas "
        f"o problemas visuales, quedando{len(retained)} provisionales; su mediana a L*<35 es{qc['35']['median']*100:.1f}% "
        f"y a L*<45,{qc['45']['median']*100:.1f}%. No equivale a validar humanamente todas las restantes.",
        '', '## Comparación con clases próximas','',
        '| Clase/subconjunto | Cajas | Mediana L*<35 en máscara aproximada | Mediana L*<45 |','|---|---:|---:|---:|']
    for name in NAMES:
        c=raw['classes'][name];lines.append(f"| {name} | {c['n_boxes']} | {c['approximate_surface']['35']['median']*100:.1f}% | {c['approximate_surface']['45']['median']*100:.1f}% |")
    lines+=['', 'Las regiones oscuras no son exclusivas de Sobremadura y esta medida no aumenta '
        'monótonamente con la clase. Los capachos verdes pueden ser más oscuros de base; hay '
        'sombras, venas y oclusiones en todas las clases. En la comparación emparejada de '
        'regiones centrales de la misma foto, la mediana Sobre−Pintona es−6,0pp (116pares) '
        'y Sobre−Madura−1,4pp (81pares). No se interpreta como menos deterioro fisiológico.',
        '', 'El grupo `component_35` aporta266 de363 cajas Sobremadura (73,3%), y `component_2` '
        'otras69. Las observaciones pueden repetir plantas/órganos en fotogramas: son '
        'descriptores del train actual, no una estimación de frecuencia en cultivo.',
        '', '![Distribuciones y sensibilidad](../../outputs/calyx_dark_regions_train_20261031/coverage_summary.png)',
        '', '## Ejemplos con porcentajes','',
        'Se muestran seis Sobremaduras de train, seleccionadas para ilustrar desde poca oscuridad '
        'hasta casos extensos, no al azar. La última es un contraejemplo de oscuridad global: '
        'no se certifica como mancha. Verde: contorno estimado; magenta: píxeles L*<35.',
        '', '![Ejemplos medidos](../../outputs/calyx_dark_regions_train_20261031/examples_quantified.png)',
        '', '## Localización próxima al pedicelo','',
        'Las cajas originales no contienen orientación anatómica ni punto de unión. No se '
        'supone que arriba en la foto sea proximal para las363 cajas. En un ejemplo con '
        'pedicelo visible (`row_0297_box_000`) se estimó visualmente su dirección; no es '
        'una anotación humana validada ni un resultado poblacional.',
        '', f"En ese caso, la zona proximal definida como30% del recorrido proyectado de la máscara "
        f"tiene{axial['proximal']['absolute_dark_fraction']['35']*100:.0f}% de píxeles L*<35, frente a "
        f"{axial['remaining']['absolute_dark_fraction']['35']*100:.0f}% en el resto. Al rotar la dirección estimada±15°, "
        f"el valor proximal varía entre{min(axial['proximal_dark35_rotation_sensitivity'])*100:.0f} y{max(axial['proximal_dark35_rotation_sensitivity'])*100:.0f}%. "
        'Sirve como ilustración de distribución espacial, no para calibrar una regla universal.',
        '', '![Zona proximal ilustrativa](../../outputs/calyx_dark_regions_train_20261031/proximal_example.png)',
        '', '## Consecuencia para el generador','',
        'Conviene variar de forma independiente la cobertura, la intensidad y la posición del '
        'oscurecimiento: mantener ejemplos claros y generar también manchas localizadas y '
        'coberturas extensas. Pintona y Madura pueden tener oscurecimiento proximal; no debe '
        'ser un marcador exclusivo de Sobremadura. El porcentaje de píxeles oscuros no se '
        'convierte directamente en severidad del modelo, tamaño, edad o reabsorción.',
        '', 'Antes de fijar distribuciones de pigmentación hacen falta máscaras visibles revisadas '
        'y atributos separados de sombra, manchas/venación, cobertura por hojas y punto proximal. '
        'Este análisis no modifica categorías, entrenamiento, plantas o imágenes; tampoco '
        'reanuda generación. Las503 imágenes/20plantas siguen preservadas y la campaña pausada.',
        '', 'Artefactos: `input_lock.json`, `measurements.json`, `summary.json`, `reviewed_summary.json`, '
        'máscaras/crops por objeto e `index.html`. Semilla20261031, scripts/versiones y hashes '
        'registrados; tres pruebas de fracción, umbral relativo y máscara geométrica pasaron.']
    doc.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    page='<html lang="es"><meta charset="utf-8"><title>Oscuridad en capachos de train</title><style>body{font:18px system-ui;max-width:1600px;margin:auto;padding:25px}img{max-width:100%}</style><h1>Cuantificación exploratoria</h1><p>363 Sobremaduras en170 fotos de train;116 Pintona y81 Madura de las mismas fotos. Máscaras aproximadas, no ground truth. Oscuridad fotografiada incluye iluminación y oclusores; no es una medida de lesión.</p>'
    for title,file in [('Distribución de cobertura','coverage_summary.png'),('Ejemplos y sensibilidad al umbral','examples_quantified.png'),('Un ejemplo proximal orientado visualmente','proximal_example.png')]:page+=f'<h2>{title}</h2><img src="{file}">'
    page+='<h2>Revisión de máscaras</h2><p>Cian: región central; verde: máscara aproximada; magenta: oscuridad L*<35. Incluye fallos conservados.</p>'
    for p in sorted(out.glob('review_page_*.png')):page+=f'<img src="{p.name}">'
    (out/'index.html').write_text(page+'</html>',encoding='utf-8')
    graphpath=repo/'docs/repository_context_graph.json';shutil.copy2(graphpath,out/'graph_before.json');g=read(graphpath)
    g['nodes'].append(dict(id='entrypoint.train_calyx_darkness',type='entrypoint',label='Cuantificacion train-only de oscuridad visible del capacho',
        summary='Cribado exploratorio de363 Sobre/170fotos y197controles mismafoto. L*25/35/45 en elipse central y GrabCut aproximado; oscuridad no equivale a pigmentacion/lesion. RevisionCodex de30casos detecta tejido omitido y hojas incluidas; no son masksGT. Cobertura amplia existe, distribucion no exclusiva de Sobre. Un ejemplo proximal orientado visualmente; nunca asumir arriba=proximal en todas las cajas. Fuentes/datos originales intactos; banco pausado y sin entrenamiento.',
        paths=['scripts/quantify_calyx_dark_regions.py','scripts/report_calyx_dark_regions.py','tests/test_calyx_dark_regions.py',str(doc.relative_to(repo)).replace('\\','/')],
        evidence=[dict(path='scripts/quantify_calyx_dark_regions.py',locator='def darkness_metrics('),dict(path='scripts/report_calyx_dark_regions.py',locator='no_anatomical_orientation_assumed_for_population'),dict(path='tests/test_calyx_dark_regions.py',locator='def test_uniform_dark_is_not_lost_by_relative_threshold(')]))
    g['edges'].append(dict(source='entrypoint.train_calyx_darkness',target='entrypoint.calyx_deterioration_visual_pilot',relation='constrains_visible_darkness_hypotheses_without_class_exclusivity_or_physiological_inference',
        evidence=[dict(path=str(doc.relative_to(repo)).replace('\\','/'),locator='## Consecuencia para el generador')]))
    write(graphpath,g)
    bank=repo/'outputs/spatial_dataset_completion_20261030';require(read(bank/'pause_requested.json')['active'],'Generation unexpectedly released')
    verify_sources(repo/'outputs/reviewed_augmentation_115_20261031')
    for row in read(out/'input_lock.json')['records']:
        for kind in ('image','label'):require(sha(row[kind])==row[kind+'_sha256'],'Input changed')
    files=[doc,graphpath,out/'input_lock.json',out/'summary.json',out/'measurements.json',out/'reviewed_summary.json',out/'index.html',Path(__file__),repo/'scripts/quantify_calyx_dark_regions.py',repo/'tests/test_calyx_dark_regions.py',*out.glob('*.png')]
    snap=out/'source_snapshot';snap.mkdir()
    for path in files:
        if path.suffix=='.py':shutil.copy2(path,snap/path.name)
    write(out/'completion.json',dict(completed=True,only_train=True,validation_or_test_pixels_read=False,
        generation_paused=True,new_renders=0,new_training_runs=0,seed=20261031,
        script_version='calyx-darkness-screening/1',parameter_preset='Lstar25_35_45_core_and_approximate_grabcut',
        original_labels_modified=False,mask_validation='provisional_Codex_screening_not_human_ground_truth',
        artifacts={str(p):sha(p) for p in files},finished_utc=time.time()))
    print('QC',len(excluded),'excluded approximate masks;',len(retained),'provisional remaining; medians',qc)
    print('Proximal example',axial)
    print('Report complete; source labels and paused bank unchanged')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out',type=Path);a=p.parse_args();run(a.out.resolve())
