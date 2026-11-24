"""Package measured pilot results, review queues, and limitations in Spanish."""
from collections import Counter
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import shutil
import subprocess

import cv2
from prepare_union_pilot import ROOT, sha, write


def main():
    status=json.loads((ROOT/'pipeline_status.json').read_text())
    if status['stage']!='completed':raise RuntimeError('Pipeline not complete')
    arms=status['arms']
    readiness=json.loads((ROOT/'readiness.json').read_text())
    metrics=json.loads((ROOT/'evaluation/summary.json').read_text())
    lock=json.loads((ROOT/'evaluation_lock.json').read_text())
    report=ROOT/'delivery';report.mkdir(exist_ok=True)
    videos={arm:json.loads((ROOT/'videos'/arm/'summary.json').read_text()) for arm in arms}
    deliveries=[]
    for index,name in enumerate(['125180','125181','125182']):
        if 'mixed' in arms:
            target=report/f'{name}_comparacion_real_mixto.mp4'
            if not target.exists():
                subprocess.run([shutil.which('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error',
                    '-i',videos['real'][index]['video_path'],'-i',videos['mixed'][index]['video_path'],
                    '-filter_complex','[0:v][1:v]hstack=inputs=2[v]','-map','[v]',
                    '-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart',str(target)],check=True)
        else:
            target=report/f'{name}_real_annotated.mp4'
            if not target.exists():shutil.copy2(videos['real'][index]['video_path'],target)
        cap=cv2.VideoCapture(str(target));frame_count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));fps=cap.get(cv2.CAP_PROP_FPS)
        assert frame_count==videos['real'][index]['frames'] and abs(fps-5)<.01
        cap.set(cv2.CAP_PROP_POS_FRAMES, min(100,frame_count-1));ok,frame=cap.read();cap.release()
        if not ok:raise RuntimeError('Delivery video not decodable')
        cv2.imwrite(str(report/f'{name}_preview.jpg'),frame)
        deliveries.append({'video':name,'path':str(target.resolve()),'sha256':sha(target),'frames':frame_count,'fps':fps})
    lines=['# Piloto real depurado y ArUco — 22 de octubre de 2026','',
           '## Resultado y alcance','',
           'Se completó la preparación del dataset, el entrenamiento y la evaluación técnica. '
           'Los resultados de detección cuantitativos corresponden a la prueba real agrupada de desarrollo; '
           'los videos nuevos no tienen anotaciones exhaustivas, por lo que no se informa AP externo. '
           'La salida respecto a ArUco contiene desplazamientos en imagen, no posiciones 3D ni exactitud métrica validada.','',
           '## Datos y procedencia','',
           'Fuente local: `union_anotadas_20261021_local_v1`, exportación `latest` preservada por hash; '
           'no se certificó identidad con la v1 publicada en Ultralytics. Originales conservados. '
           'Se excluyeron 22 imágenes completas por 25 polígonos y se separaron ocho copias exactas. '
           'Quedaron 643 imágenes, con grupos por prefijo de secuencia, duplicados y unión conservadora de candidatos dHash; '
           'fotografías sin grupo verificable se restringieron a entrenamiento. La independencia por sesión no está demostrada.','',
           '| Split | Imágenes | Pintona | Madura | Sobremadura |','|---|---:|---:|---:|---:|']
    for split,c in readiness['counts'].items():lines.append(f"| {split} | {c['images']} | "+' | '.join(map(str,c['classes']))+' |')
    lines+=['','Las proporciones resultantes son 71,70/13,69/14,62 %, con desviaciones de +1,70/−1,31/−0,38 puntos '
            'frente a 70/15/15. Se priorizó mantener grupos indivisibles y las tres clases. Las 251 fotografías sin secuencia '
            'verificable quedaron en entrenamiento; validación y test contienen secuencias identificadas por nombre, '
            'sin afirmar independencia por sesión. `group_split_summary.json` conserva los prefijos y componentes.','',
            'Los tres videos y el Excel se copiaron a `inputs/` con SHA-256, sin editar las fuentes. '
            'El CSV y la galería `review/` dejan decisiones pendientes para Karen y Caroline; no se enviaron mensajes.','',
            '## Entrenamiento y controles','',
            'Inicialización común `yolo26n.pt`; semilla 20261022; entrada 960; batch 2; AdamW LR 0,0002, nbs=2 y sin warmup. '
            'Aumentación nativa: HSV solo valor 0,1 y reflejo horizontal 0,5. Sin mosaic, mixup, copy-paste, traslación, escala aleatoria, rotación ni perspectiva. '
            'Se verificaron las transformaciones nativas y su ausencia en validación, así como cambios de parámetros y pasos efectivos del optimizador.','',
            '| Brazo | Épocas registradas | Pasos efectivos | Segundos | SHA-256 best |','|---|---:|---:|---:|---|']
    for arm in arms:
        c=json.loads((ROOT/'training'/arm/'completion.json').read_text())
        lines.append(f"| {arm} | {len(c['epochs'])} | {c['optimizer_steps']} | {c['seconds']:.1f} | `{c['best_sha256']}` |")
    if 'mixed' in arms:
        mixture=json.loads((ROOT/'mixed_dataset/manifest.json').read_text())
        lines+=['','La mezcla usa 384 imágenes reales y 96 sintéticas (80/20 por imágenes), todas las sintéticas proceden de '
                'las vistas train existentes con semillas 814200–814203. Se comprobaron IDs raster, número de píxeles y cajas contra máscaras nativas. '
                f"Instancias reales: {sum(mixture['annotation_counts']['real'].values())}; sintéticas: {sum(mixture['annotation_counts']['synthetic'].values())}. "
                'La exposición por instancia no es 80/20 y hay menos exposición real que en real-only. '
                'Las clases sintéticas siguen siendo aproximaciones de apariencia; no hay madurez agronómica medida. '
                'No se generaron renders.','',
                f"Presupuesto de pasos emparejado: **{metrics['comparison']['equal_optimizer_steps']}**. "
                'Los checkpoints se seleccionaron por validación bajo la misma política; pueden corresponder a épocas diferentes.']
    lines+=['','## Detección en prueba agrupada','',
            f"Confianza común {lock['confidence']:.6f}, seleccionada solo con F1 medio de validación del brazo real; "
            'matching IoU 0,5, entrada 960 y configuración de inferencia común. AP se calcula con barrido de confianza. '
            'Se preservan por separado localización colapsada y clasificación.','',
            '| Brazo | AP50–95 macro | AP50 | AP50–95 colapsado | Precisión micro fija | Recall micro fijo |',
            '|---|---:|---:|---:|---:|---:|']
    for arm in arms:
        m=metrics[arm];fixed=m['fixed_threshold']['class_aware']
        lines.append(f"| {arm} | {m['test']['map50_95']:.4f} | {m['test']['map50']:.4f} | "
                     f"{m['test_class_collapsed']['map50_95']:.4f} | {fixed['micro_precision']:.4f} | {fixed['micro_recall']:.4f} |")
    lines+=['','| Brazo | Clase | AP50–95 | AP50 | Precisión fija | Recall fijo |','|---|---|---:|---:|---:|---:|']
    names=['Pintona','Madura','Sobremadura']
    for arm in arms:
        for row in metrics[arm]['test']['per_class']:
            cid=row['class_id']; fixed=metrics[arm]['fixed_threshold']['class_aware']
            lines.append(f"| {arm} | {names[cid]} | {row['ap50_95']:.4f} | {row['ap50']:.4f} | "
                         f"{fixed['precision'][cid]:.4f} | {fixed['recall'][cid]:.4f} |")
    if 'mixed' in arms:
        delta=metrics['comparison']['delta_map50_95']
        lines+=['',f'Variación mezcla − real: **{delta:+.4f} AP50–95** ({delta*100:+.2f} puntos porcentuales). '
                'Es un piloto de una semilla y una partición; no demuestra significancia estadística ni transferencia a sesiones independientes. '
                'No se reajustaron modelos después de consultar test.']
        if delta <= 0:
            lines+=['','**La mezcla no mejoró AP50–95 macro en este piloto.** Se conserva como resultado negativo; '
                    'no se promueve el brazo sintético como reemplazo del detector real.']
    lines+=['','## Videos, ArUco y referencias manuales','',
            'Se procesaron los tres videos completos a 5 fps, con índices de frame y timestamps originales. '
            'Los IDs de tracking se asignan por IoU y expiran tras un segundo; sus duraciones son descriptivas, no métricas MOTA/IDF1. '
            'Los candidatos ArUco se filtran por tamaño, convexidad y degeneración. Las esquinas pueden propagarse por flujo óptico '
            'durante un máximo de un segundo con control bidireccional, siempre marcado como propagado. '
            'Esta inspección técnica de marcadores utilizó los propios videos y no constituye validación externa del estimador de pose.','',
            '| Video | Frames a 5 fps | Referencia observada | Observada o propagada | Detecciones real | Detecciones mixto |',
            '|---|---:|---:|---:|---:|---:|']
    for i,name in enumerate(['125180','125181','125182']):
        r=videos['real'][i];mixed_count=videos['mixed'][i]['detections'] if 'mixed' in videos else 'no ejecutado'
        lines.append(f"| {name} | {r['frames']} | {r['frames_with_observed_marker']} | {r['frames_with_any_reference']} | {r['detections']} | {mixed_count} |")
    lines+=['','| Brazo | Video | Tracks | Mediana de observaciones/track | Tracks con ≥5 observaciones |',
            '|---|---|---:|---:|---:|']
    for arm in arms:
        for r in videos[arm]:
            lines.append(f"| {arm} | {r['video']} | {r['track_count']} | {r['track_observation_count_median']} | {r['tracks_seen_at_least_5_frames']} |")
    lines+=['','Los conteos son observaciones por frame, **no frutos únicos ni aciertos**. '
            'La cobertura de ArUco corresponde al detector y sus filtros; no certifica precisión de IDs contra anotación humana exhaustiva. '
            'Un número mayor de detecciones no demuestra mejora. Cada predicción contiene desplazamiento X derecha/Y arriba respecto a los centros '
            'de marcadores visibles, en píxeles y normalizado por su tamaño aparente. Z permanece ausente. '
            'No se infiere pertenencia botánica al marcador por cercanía.','',
            'Inspección cualitativa del agente: en `125180` y `125181` a 19,79 s, y en `125182` a 59,79 s, '
            'se observan capachos visibles sin caja y cajas sobre zonas foliares. Las vistas amplias y las referencias '
            'parcialmente recortadas son casos difíciles conservados en los videos. Esta revisión es puntual, '
            'no anotación humana exhaustiva ni una medida de recall externo.','',
            'Se preservaron las celdas del Excel y 32 referencias XYZ del bloque N:Q de Hoja 2, con unidades cm confirmadas por el usuario. '
            'Los demás bloques siguen disponibles íntegros en `workbook_cells.json`. M0/M1 son resultados históricos, no predicciones de este piloto. '
            'No se reutilizaron los porcentajes de precisión del libro ni se sustituyeron ausencias por cero. '
            'El archivo `fruit_identity_review.csv` deja pendientes la correspondencia visual de cada fruto, video/timestamp y origen.','',
            'La convención solicitada es X derecha, Y arriba, Z hacia adentro. No se estimó una transformación física válida: '
            'el origen no está confirmado, falta calibración de cámara y el lado negro del ArUco no se conoce. '
            'A4 no fija ese lado; las hojas observadas presentan curvatura, oclusión o recortes, por lo que no se promovió una escala fiable. '
            'El contrato de signos conserva Z hacia adentro y cambia el signo de Y respecto a una cámara derecha/abajo/adelante; '
            'esa conversión tiene determinante −1 y no es una rotación de pose. Se probó la conversión de desplazamientos '
            'de metros a centímetros como fixture, sin aplicarla a coordenadas 3D inexistentes. '
            '**No hay errores XYZ en centímetros ni error de reproyección de pose disponible.** '
            'Incluso con pose métrica del marcador, el centro de una caja en una sola imagen no fija la profundidad del fruto; '
            'no se asumió que los frutos sean coplanares con la hoja. '
            'No se asociaron frutos minimizando distancia contra la verdad manual.','',
            '## Entrega y continuidad','',
            '- `dataset/`: imágenes y cajas depuradas; `manifest.json` y `readiness.json`: procedencia y controles.',
            '- `review/`: CSV de duplicados, imágenes excluidas y revisión de polígonos con recortes.',
            '- `training/<brazo>/weights/best.pt`: pesos seleccionados; `completion.json`, configuración y evidencia del optimizador.',
            '- `evaluation/`: AP por clase/colapsado, matrices y predicciones con umbral congelado.',
            '- `videos/`: observaciones por frame, tracking, referencias observadas/propagadas y videos individuales.',
            '- `delivery/`: tres videos comparativos (real a la izquierda, mixto a la derecha cuando existe) e índice HTML.',
            '- `references/`: Excel extraído y lista de identidades por confirmar.','',
            'Pruebas específicas: diez pruebas aprobadas, incluidas las ocho del piloto sobre cajas, particiones, aumentación nativa, '
            'ejes y unidades, referencias ausentes, rechazo de marcadores degenerados y separación entre localización/clasificación, '
            'más dos de auditoría. '
            'El validador del grafo conserva los diez localizadores preexistentes rotos; '
            'no se presenta como exitoso ni se modificaron cambios ajenos. No se instalaron dependencias ni se publicaron cambios.','',
            'Siguiente paso: adjudicar polígonos e identidades con Karen y Caroline, medir el cuadrado negro y calibrar la cámara; '
            'después fijar el origen físico y reconstruir con correspondencias multivista o profundidad medida, '
            'para evaluar métricamente sin usar las coordenadas verdaderas como entrada del estimador.','',
            'Cierre UTC: '+datetime.now(timezone.utc).isoformat()]
    text='\n'.join(lines)+'\n'
    (ROOT/'INFORME.md').write_text(text,encoding='utf-8')
    doc=Path('docs/reports/piloto_real_union_aruco_2026-10-22.md')
    if doc.exists():raise FileExistsError(doc)
    doc.write_text(text,encoding='utf-8')
    cards=''.join(f'<section><h2>{r["video"]}</h2><video controls preload="metadata" poster="{r["video"]}_preview.jpg" src="{html.escape(Path(r["path"]).name)}"></video></section>' for r in deliveries)
    page='<meta charset="utf-8"><title>Piloto uchuva: real y mixto</title><style>body{font:17px sans-serif;max-width:1400px;margin:32px auto;background:#f4f6f4;color:#173020}video{width:100%}section{margin:32px 0}a{color:#185c43}</style><h1>Piloto real depurado y comparación sintética</h1><p>Izquierda: real. Derecha: mezcla. Referencias ArUco en imagen; no hay posición 3D validada.</p><p><a href="../INFORME.md">Informe completo</a> · <a href="../review/index.html">Revisión de polígonos</a></p>'+cards
    (report/'index.html').write_text(page,encoding='utf-8')
    write(report/'manifest.json',{'videos':deliveries,'report_sha256':sha(ROOT/'INFORME.md'),
          'completed_at_utc':datetime.now(timezone.utc).isoformat(),'deadline_utc':'2026-10-22T12:30:00+00:00'})
    print('Delivery complete:',report)


if __name__=='__main__':main()
