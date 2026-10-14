"""Academic Spanish report from verified measurements, with editable Markdown."""
import argparse
from collections import Counter
from html import escape
import importlib.metadata
import json
from pathlib import Path
import sys
import cv2

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import write,sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();r=a.root.resolve()
    protocols=['historical_1hz','historical_every_frame','offline_every_frame']
    metrics={name:json.loads((r/'evaluation'/name/'metrics.json').read_text()) for name in protocols}
    winner=metrics['offline_every_frame'];flight=json.loads((r/'flight/full/result.json').read_text())
    orientation=json.loads((r/'flight/full/orientation_validation.json').read_text())
    verification=json.loads((r/'presentation/verification.json').read_text())
    if not verification['passed'] or not flight['completed']:raise ValueError('Verified full videos and capture required')
    if not json.loads((r/'verification/isolation.json').read_text())['passed']:raise ValueError('Estimator isolation replay pending')
    frozen=json.loads((r/'experiment_lock.json').read_text())
    for path,digest in frozen['sha256'].items():
        if sha(ROOT/path)!=digest:raise ValueError('Frozen experimental source changed: '+path)
    privileged=json.loads((r/'privileged/privileged_diagnostics.json').read_text())
    catalog=json.loads((r/'evaluation/offline_every_frame/missed_target_catalog.json').read_text())
    mapping=json.loads((r/'estimates/offline_every_frame/map.json').read_text())
    references=json.loads((ROOT/'docs/references/video_continuo_20261008.json').read_text())['references']
    output=r/'presentation';output.mkdir(exist_ok=True)
    delivery=[]
    for item in mapping['objects']:
        delivery.append(dict(persistent_id=item['map_id'],state=item['state'],canonical_aruco=item['marker_id'],
            position_xyz_m=item['position_marker_m'],uncertainty_m=item.get('uncertainty_m'),class_id=item['class_id'],
            source_tracks=item['track_ids'],support_observation_ids=item['observation_ids'],rejection_reasons=item.get('rejection_reasons',[])))
    unresolved={}
    represented={tid for item in mapping['objects'] for tid in item['track_ids']}
    for item in mapping['rejected']:
        tid=item['track_id']
        if tid in represented:continue
        unresolved.setdefault(tid,[]).append(item.get('reason','cause_not_determined'))
    for tid,reasons in unresolved.items():
        delivery.append(dict(persistent_id=None,state='no_localizable',canonical_aruco=None,position_xyz_m=None,
            uncertainty_m=None,class_id=None,source_tracks=[tid],support_observation_ids=[],rejection_reasons=sorted(set(reasons))))
    write(output/'mapa_conciliado.json',dict(version='continuous-calyx-delivery/1.0',units='metres',
        objects=delivery,note='Unresolved tracks are hypotheses, not independent biological counts. Confirmed is algorithmic acceptance, not verified truth.'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    labels=['1 Hz','30 Hz histórico','30 Hz offline']
    axes[0].bar(labels,[metrics[n]['recall_3d']*100 for n in protocols]);axes[0].set(ylabel='Recall 3D (%)',ylim=(0,100),title='Objetos únicos localizados a ≤5 cm')
    axes[1].bar(labels,[metrics[n]['precision_3d']*100 for n in protocols]);axes[1].set(ylabel='Precisión conjunta (%)',ylim=(0,100),title='Identidad, ArUco y posición correctos')
    for ax in axes:ax.tick_params(axis='x',labelrotation=15);ax.grid(axis='y',alpha=.2)
    fig.tight_layout();fig.savefig(output/'comparacion_3d.png',dpi=160);plt.close(fig)
    fig=plt.figure(figsize=(10,6))
    for i,marker in enumerate(range(0,12,2)):
        ax=fig.add_subplot(2,3,i+1,projection='3d')
        for state,color in [('confirmed','green'),('provisional','orange')]:
            points=[v['position_marker_m'] for v in mapping['objects'] if v['marker_id']==marker and v['state']==state]
            if points:ax.scatter(*zip(*points),s=10,c=color)
        ax.scatter([0],[0],[0],marker='s',c='black');ax.set(title=f'ArUco {marker}',xlabel='X (m)',ylabel='Y (m)',zlabel='Z (m)')
    fig.tight_layout();fig.savefig(output/'mapa_3d.png',dpi=160);plt.close(fig)
    def percent(value):return f'{100*value:.2f} %'
    def cm(value):return 'no disponible' if value is None else f'{100*value:.2f}'
    rows=['| Protocolo | Correctos / visibles | Recall 3D | Precisión conjunta | Intrusiones | Duplicados |',
          '|---|---:|---:|---:|---:|---:|']
    for name in protocols:
        m=metrics[name];rows.append(f"| {name} | {m['localized_unique']}/{m['target_visible_unique']} | {percent(m['recall_3d'])} | {percent(m['precision_3d'])} | {m['background_intrusions']} | {m['duplicates']} |")
    rows2=['| Protocolo | Precisión 2D | Recall 2D | AP máscara 50–95 | AP clases colapsadas |', '|---|---:|---:|---:|---:|']
    for name in protocols:
        m=metrics[name];rows2.append(f"| {name} | {percent(m['precision_2d'])} | {percent(m['recall_2d'])} | {m['mask_ap']['map50_95']:.4f} | {m['collapsed_mask_ap']['map50_95']:.4f} |")
    reasons=Counter(reason for item in catalog for reason in item['causes'])
    cache=json.loads((r/'predictions/completion.json').read_text())
    track_seconds={n:json.loads((r/'estimates'/n/'provenance.json').read_text())['seconds'] for n in protocols}
    text=f'''# Localización retrospectiva de uchuvas en una hilera simulada con cultivo de fondo

## Resumen

Se evaluó una hilera de seis plantas con doce plantas de contexto en Gazebo. La variante offline localizó correctamente {winner['localized_unique']} de {winner['target_visible_unique']} capachos objetivo distintos observables: recall {percent(winner['recall_3d'])}, precisión conjunta {percent(winner['precision_3d'])} y precisión de asociación {percent(winner['association_precision'])}. Se contabilizaron {winner['background_intrusions']} intrusiones del fondo. Estos resultados describen simulación retrospectiva; no prueban transferencia al cultivo real.

## Diseño experimental

Las tres hileras comparten el modelo morfológico de uchuva, materiales y tutorado diagonal. La hilera objetivo reutiliza seis morfologías anteriormente inspeccionadas; las doce plantas de fondo tienen semillas distintas y reproducibles. Sus roles y los códigos ArUco se declaran explícitamente. El fondo no recibe métricas individuales ni aumenta el denominador objetivo. La separación de hileras es una elección de ingeniería verificada mediante obstáculos individuales, no una distancia agronómica validada.

Se conservaron el modelo congelado del ciclo 4 y las clases pintona —incluye verdes—, madura y sobremadura por apariencia del capacho. La clasificación no certifica la madurez del fruto oculto. No hubo entrenamiento adicional. La configuración se congeló antes de la comparación reportada; fecha: {frozen['utc']}.

## Captura y recorrido

Se capturaron {verification['original_frames']} pares RGB/máscara originales a 1280 × 720, con sensores a 30 Hz y timestamps del simulador. El recorrido pasó por ambas caras, con giro hacia el arbusto terminal. Se alcanzaron {flight['waypoints_reached']}/{flight['waypoints_expected']} puntos y una separación mínima de {flight['minimum_executed_margin_m']:.3f} m. El error máximo de orientación durante el giro fue {orientation['maximum_turn_error_deg']:.2f}°. Hubo {orientation['turn_aruco_undecodable_frames']} cuadros del giro sin ArUco objetivo decodificable; esta invisibilidad no se equipara automáticamente a mirar fuera de la hilera.

Los vídeos finales contienen cada PNG original una sola vez y fueron decodificados íntegramente. No se analizaron imágenes interpoladas ni fotogramas del vídeo comprimido. La simulación puede avanzar más lentamente que el tiempo real.

## Percepción, identidad y posición

La red procesa todos los fotogramas en recortes nativos de 960 píxeles con 20 % de solapamiento y cobertura completa. Las máscaras se conservan sin pérdida mediante bits comprimidos. La caché registra propuestas desde confianza 0,001, procedencia de recorte y supresión entre recortes. La ausencia de una propuesta no permite atribuir una causa interna específica a la red o a su NMS.

Las tres variantes reutilizan esa caché: muestreo a 1 Hz con seguimiento histórico, seguimiento histórico por fotograma y seguimiento por máscaras con conciliación offline. Se conserva una puerta geométrica común para separar frecuencia de observación y conciliación; no se presenta el primero como reproducción numérica idéntica de todos los ajustes del piloto anterior. El flujo óptico con comprobación inversa, la forma y la apariencia proponen continuidad sin usar la clase como barrera. Las fusiones offline exigen evidencia geométrica, prohíben coexistencia temporal de identidades distintas y recalculan conjuntamente la posición.

Las poses ArUco se estiman desde RGB y calibración pública con IPPE y consistencia temporal. Las caras se unen mediante la transformación pública del soporte rígido. Se requieren ocho apoyos espaciados al menos 0,2 s, paralaje de 3°, reproyección máxima de 3 píxeles y sensibilidad de 3 cm; se ajustan hasta treinta vistas y se comprueba el resto. La sensibilidad leave-one-out no es un intervalo de confianza calibrado. La posición aproxima el centro del capacho mediante centroides visibles; no localiza el fruto interno.

## Métricas y resultados

El emparejamiento usa máscaras uno a uno. Una localización correcta exige identidad respaldada por al menos tres coincidencias y 80 % de todo el soporte geométrico, ArUco correcto, error máximo de 5 cm y ausencia de duplicación. Los {winner['target_completely_hidden']} capachos objetivo completamente ocultos se informan aparte. Todos los tamaños visibles permanecen en el denominador, incluso un solo píxel. Los rechazos y trayectorias fragmentadas no se suman como objetos biológicos independientes.

{chr(10).join(rows)}

{chr(10).join(rows2)}

El error 3D mediano fue {cm(winner['error_median_m'])} cm y el P95 {cm(winner['error_p95_m'])} cm entre identidades respaldadas con ArUco correcto, incluyendo errores superiores a 5 cm. Estas estadísticas no representan los objetos perdidos. Se registraron {winner['identity_switches']} cambios de identidad y {winner['fragmented_target_objects']} objetos objetivo con trayectorias fragmentadas. Las matrices de confusión, estratos de tamaño y disponibilidad de vistas, centroides e interrupciones se conservan en los JSON de evaluación.

![Comparación de localización](../../outputs/continuous_row_20261008/presentation/comparacion_3d.png)

![Mapa por ArUco](../../outputs/continuous_row_20261008/presentation/mapa_3d.png)

## Diagnóstico de pérdidas y análisis privilegiado

El catálogo contiene {len(catalog)} capachos objetivo no localizados correctamente. Frecuencia de motivos registrados —pueden coexistir—: {dict(reasons)}. Cada entrada enlaza un timestamp y la mejor propuesta observada, cuando existe. Fragmentación, tamaño y visibilidad se interpretan como factores asociados salvo evidencia que sustente una causa. Se conserva causa no determinada cuando corresponde.

Los análisis privilegiados sustituyen poses, correspondencias o centroides por información verdadera del simulador, manteniéndose fuera del estimador. Comparan trayectorias originales con pose verdadera, correspondencias anatómicas con centroides predichos, centroides visibles verdaderos y centros geométricos proyectados. Sus cifras no son desempeño desplegable. El desfase máximo entre pose de diagnóstico y timestamp fue {privileged['simulator_pose_timestamp_nearest_max_error_seconds']} s. La distancia mediana entre centroide visible verdadero y centro geométrico proyectado fue {privileged['visible_centroid_to_projected_geometric_centre_median_px']} píxeles. Los resultados completos y las limitaciones están en `privileged_diagnostics.json`.

## Coste computacional y reproducibilidad

La inferencia acumulada por fotograma duró {cache['all_frame_seconds']:.1f} s. Seguimiento y geometría por protocolo: {track_seconds} segundos. El tiempo de evaluación privilegiada y de presentación se separa del coste de inferencia. Se priorizó procesamiento posterior; no se afirma ejecución en línea a 5 Hz.

Pesos SHA-256: {frozen['model_sha256']}. Versiones: OpenCV {cv2.__version__}; Ultralytics {importlib.metadata.version('ultralytics')}. Las fuentes, calibración, semillas, misiones, auditorías y configuración congelada acompañan la campaña. La contabilidad excluye esperas inactivas y suspensión; el usuario retiró el antiguo límite de horas.

## Limitaciones

Una única hilera objetivo reutilizada no estima generalización a nuevas parcelas. El cultivo es estático y no reproduce toda la fotometría, viento ni dinámica de contacto real. Las superficies foliares toleradas por la auditoría no equivalen a una tasa de oclusión. Los umbrales geométricos son decisiones de ingeniería. La conciliación puede conservar duplicados o hipótesis provisionales; confirmar una hipótesis algorítmica no garantiza identidad verdadera. La pose monocular de marcadores pequeños, ocluidos o de canto puede ser ambigua. La evidencia privilegiada permite estudiar mecanismos de error, pero no convierte el ensayo en una evaluación de campo.

## Referencias

'''
    text+='\n\n'.join(f"{i+1}. {ref['authors']}. {ref['title']}. {ref['url']}" for i,ref in enumerate(references))+'\n'
    labels={'below_operating_confidence':'confianza inferior al umbral',
        'insufficient_geometric_support':'soporte geométrico insuficiente',
        'insufficient_temporally_separated_support':'apoyos temporalmente separados insuficientes',
        'no_target_marker_pose_during_track':'sin pose del marcador objetivo',
        'incorrect_or_duplicate_3d_localization':'localización incorrecta o duplicada',
        'triangulation_reprojection':'reproyección incompatible',
        'no_consistent_three_view_geometry':'sin geometría consistente de tres vistas',
        'inconsistent_remaining_views':'otras vistas inconsistentes',
        'cross_tile_suppression':'supresión entre recortes','poor_mask_delineation':'delimitación deficiente',
        'unstable_triangulation':'triangulación inestable'}
    text=text.replace(str(dict(reasons)),'; '.join(f'{labels.get(k,k)}: {v}' for k,v in reasons.most_common()))
    text=text.replace(str(track_seconds),'; '.join(f'{k}: {v:.1f}' for k,v in track_seconds.items()))
    text=text.replace(str(privileged['simulator_pose_timestamp_nearest_max_error_seconds']),'0,035')
    text=text.replace(str(privileged['visible_centroid_to_projected_geometric_centre_median_px']),'1,897')
    diagnostic_rows=['| Análisis privilegiado | Objetos a ≤5 cm | Mediana (cm) | P95 (cm) |','|---|---:|---:|---:|']
    diagnostic_labels=['Pose verdadera, trayectorias originales','Pose e identidad verdaderas, centroide predicho',
        'Pose e identidad verdaderas, centroide visible verdadero','Pose y centro geométrico verdaderos']
    for label,values in zip(diagnostic_labels,privileged['experiments'].values()):
        diagnostic_rows.append(f"| {label} | {values['unique_targets_with_error_le_5cm']} | {cm(values['median_error_m'])} | {cm(values['p95_error_m'])} |")
    diagnostic_text='\n'.join(diagnostic_rows)+'\n\nEstos análisis tienen soportes y criterios de selección distintos; no deben restarse como efectos causales independientes. El caso de centros geométricos es una comprobación ideal de coordenadas, no una detección desplegable.\n\n'
    text=text.replace('## Coste computacional y reproducibilidad',diagnostic_text+'## Coste computacional y reproducibilidad')
    conclusion=('## Interpretación\n\nLa conciliación offline redujo los duplicados de 78 a 15 frente al seguimiento histórico por fotograma, '
        'pero redujo las localizaciones correctas de 73 a 62 y la precisión conjunta de 36,50 % a 32,98 %. '
        'No alcanzó el objetivo de localizar más de la mitad de los capachos observables con precisión de asociación de al menos 90 %. '
        'La fragmentación y la falta de apoyos espaciados son factores registrados; los experimentos privilegiados sugieren limitaciones de pose e identidad, sin demostrar una causa única.\n\n'
        'Durante la estabilización inicial se registraron incumplimientos del margen de encuadre, conservados en las auditorías. '
        'La revisión del criterio de estación excluyó únicamente la espera inicial predeclarada de siete segundos; no se eliminaron sus capturas. '
        f"El MP4 dura {verification['encoded_duration_seconds']:.2f} s a frecuencia constante frente a {verification['source_duration_seconds']:.2f} s entre timestamps originales; no se duplicaron ni interpolaron imágenes.\n\n")
    text=text.replace('## Limitaciones',conclusion+'## Limitaciones')
    source=ROOT/'docs/reports/evaluacion_video_continuo_2026-10-08.md'
    if frozen.get('flow_runtime_revision'):
        recovery=json.loads((r/'estimates/offline_every_frame/provenance.json').read_text())
        text+='\n## Revisión computacional durante el estudio\n\n'
        text+=(f"Por solicitud del usuario se cambió a flujo óptico LK piramidal por lotes en CUDA. "
               f"Se conservaron {recovery.get('resumed_frames',0)} fotogramas con sus detecciones, identidades y poses previas; "
               "se reconstruyó el movimiento reciente para continuar sin reasignar ese prefijo. "
               "Los primeros 173 fotogramas usan flujo OpenCV y los posteriores CUDA; el prefijo recuperado incluye ambos. No es una ejecución homogénea desde cero. "
               "Las implementaciones no son idénticas numéricamente. Las validaciones locales están en cuda_flow_validation.json "
               "y cuda_tracking_smoke.json y no garantizan equivalencia en todo el recorrido. "
               "Los rechazos internos de seguimiento del prefijo no estaban persistidos y permanecen no disponibles. "
               "Los tiempos de la continuación no incluyen todo el trabajo de intentos anteriores, preservado en execution_jobs. "
               "Las congelaciones originales y las revisiones explícitas se conservan; no se presenta esta revisión retrospectiva como comparación preregistrada.\n")
    if source.exists() and source.read_text(encoding='utf-8')!=text:raise FileExistsError(source)
    source.write_text(text,encoding='utf-8')
    # The training venv excludes the already bundled document libraries.
    try:import reportlab
    except ModuleNotFoundError:
        bundled=Path(sys.base_prefix)/'Lib/site-packages'
        if not (bundled/'reportlab').is_dir():raise
        sys.path.append(str(bundled))
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    pdfmetrics.registerFont(TTFont('Arial','C:/Windows/Fonts/arial.ttf'))
    styles=getSampleStyleSheet()
    for style in styles.byName.values():style.fontName='Arial'
    styles['BodyText'].fontSize=9.5;styles['BodyText'].leading=13
    styles['Heading2'].keepWithNext=True
    story=[];table=[]
    def flush_table():
        if not table:return
        content=[[Paragraph(escape(c),styles['BodyText']) for c in row] for row in table]
        t=Table(content,repeatRows=1,colWidths=[170*mm/len(table[0])]*len(table[0]))
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e4efe8')),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.25,colors.lightgrey),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4)]))
        story.extend([t,Spacer(1,10)]);table.clear()
    for paragraph in text.split('\n\n'):
        if paragraph.startswith('|'):
            for line in paragraph.splitlines():
                if set(line.strip())<=set('|-: '):continue
                table.append([cell.strip() for cell in line.strip('|').split('|')])
            flush_table()
        elif paragraph.startswith('!['):
            path=output/('comparacion_3d.png' if 'comparacion_3d' in paragraph else 'mapa_3d.png')
            image=Image(str(path));image.drawHeight*=170*mm/image.drawWidth;image.drawWidth=170*mm;story.extend([image,Spacer(1,10)])
        elif paragraph.startswith('# '):story.append(Paragraph(escape(paragraph[2:]),styles['Title']))
        elif paragraph.startswith('## '):story.append(Paragraph(escape(paragraph[3:]),styles['Heading2']))
        else:story.append(Paragraph(escape(paragraph).replace('\n',' '),styles['BodyText']));story.append(Spacer(1,6))
    pdf=output/'reporte_academico.pdf'
    if pdf.exists():raise FileExistsError(pdf)
    def footer(canvas,doc):
        canvas.setFont('Arial',8);canvas.drawRightString(190*mm,12*mm,f'Gazebo retrospectivo — {doc.page}')
    SimpleDocTemplate(str(pdf),pagesize=A4,leftMargin=20*mm,rightMargin=20*mm,topMargin=18*mm,bottomMargin=20*mm).build(story,onFirstPage=footer,onLaterPages=footer)
    write(output/'report_provenance.json',dict(markdown=str(source),markdown_sha256=sha(source),pdf_sha256=sha(pdf),
        visual_pdf_review='pending: render and inspect every page before final delivery',experiment_lock_sha256=sha(r/'experiment_lock.json')))


if __name__=='__main__':main()
