"""Build the student guide from the published, frozen result snapshot.

Requires ReportLab and Pillow already supplied by the authoring runtime.
This script does not import training or simulation code.
"""
from pathlib import Path
import csv
import json
from xml.sax.saxutils import escape
from PIL import Image as PILImage
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parent
FONT_DIR = Path('C:/Windows/Fonts')
if (FONT_DIR / 'arial.ttf').exists():
    pdfmetrics.registerFont(TTFont('Guide', str(FONT_DIR / 'arial.ttf')))
    pdfmetrics.registerFont(TTFont('GuideBold', str(FONT_DIR / 'arialbd.ttf')))
    pdfmetrics.registerFontFamily('Guide', normal='Guide', bold='GuideBold', italic='Guide', boldItalic='GuideBold')
else:
    pdfmetrics.registerFont(pdfmetrics.Font('Guide', 'Helvetica', 'WinAnsiEncoding'))
    pdfmetrics.registerFont(pdfmetrics.Font('GuideBold', 'Helvetica-Bold', 'WinAnsiEncoding'))
    pdfmetrics.registerFontFamily('Guide', normal='Guide', bold='GuideBold', italic='Guide', boldItalic='GuideBold')

styles = getSampleStyleSheet()
for name in ['Normal','BodyText','Title','Heading1','Heading2']:
    styles[name].fontName = 'Guide'
styles['BodyText'].fontSize = 10.2
styles['BodyText'].leading = 15
styles['BodyText'].spaceAfter = 8
styles['Heading1'].fontName = 'GuideBold'
styles['Heading1'].fontSize = 21
styles['Heading1'].leading = 25
styles['Heading1'].textColor = colors.HexColor('#163f45')
styles['Heading1'].spaceAfter = 16
styles['Heading2'].fontName = 'GuideBold'
styles['Heading2'].fontSize = 12
styles['Heading2'].leading = 17
styles['Heading2'].spaceBefore = 9
styles['Heading2'].spaceAfter = 6
styles.add(ParagraphStyle('SmallGuide',parent=styles['BodyText'],fontSize=8.3,leading=11.5,textColor=colors.HexColor('#44515c')))
styles.add(ParagraphStyle('TableGuide',fontName='Guide',fontSize=9,leading=12))
styles.add(ParagraphStyle('TableHeadGuide',parent=styles['TableGuide'],fontName='GuideBold',textColor=colors.white))
story=[]
outline=[]


def p(text, small=False):
    story.append(Paragraph(text,styles['SmallGuide' if small else 'BodyText']))
    outline.append(text)


def h(text):
    story.append(Paragraph(text,styles['Heading2']))
    outline.append('## '+text)


def page(title):
    if story: story.append(PageBreak())
    story.append(Paragraph(title,styles['Heading1']))
    outline.append('\n# '+title)


def table(rows, widths=None):
    cells=[[Paragraph(escape(str(v)),styles['TableHeadGuide' if i==0 else 'TableGuide']) for v in row] for i,row in enumerate(rows)]
    t=Table(cells,colWidths=widths or [495/len(rows[0])]*len(rows[0]),repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#164c52')),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#eef3f3'),colors.white]),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,-1),(-1,-1),0.5,colors.HexColor('#a2b5b9'))]))
    story.extend([t,Spacer(1,12)])
    outline.extend([' | '.join(map(str,row)) for row in rows])


def img(path,width=495,max_height=290):
    full=ROOT/path
    w,h=PILImage.open(full).size
    scale=min(width/w,max_height/h)
    story.append(Image(str(full),width=w*scale,height=h*scale,hAlign='LEFT'))
    story.append(Spacer(1,6))
    outline.append('Imagen: '+str(path))


def pct(v): return f'{100*v:.2f}%'.replace('.',',')


static=json.loads((ROOT/'metrics/static_full_views.json').read_text(encoding='utf-8'))
routes={r:json.loads((ROOT/f'metrics/{r}.json').read_text(encoding='utf-8')) for r in ['legacy','vertical','orbit']}
selection=json.loads((ROOT/'evidence/flights/example_selection.json').read_text(encoding='utf-8'))
epoch=list(csv.DictReader((ROOT/'metrics/training_results.csv').open()))[-1]
epoch={k.strip():v for k,v in epoch.items()}

page('Uchuvas sintéticas\n<br/>Guía de la campaña multiescala')
p('<b>Entrega parcial para las estudiantes · 21 de octubre de 2026</b>')
p('Esta guía explica qué se construyó, cómo se evaluó y qué puede concluirse de la campaña actual. El objetivo es facilitar la apropiación del experimento y la revisión de sus evidencias sin volver a diseñar los arbustos.')
img('images/vertical_lower_median_031.jpg',max_height=270)
p('Vista completa de inspección vertical con máscaras e identidades predichas. Los vecinos permanecen en la imagen. Los colores identifican tracks, no necesariamente las clases de apariencia.',True)
table([['Entregado en este corte','Pendiente de cierre'],['384 vistas; entrenamiento de 10 épocas; comparación estática auditada.','Video orbital con recuadro externo completo y revisado.'],['627 fotogramas de tres rutas, matrices, seguimiento y dos videos PiP completos.','Localización métrica 3D, evaluación de su error y cobertura, e informe final.']], [247.5,247.5])
p('<b>Resultado principal:</b> el nuevo modelo mejora F1 en las vistas completas de prueba de desarrollo de 51,34% a 59,86%. En vuelo, los acercamientos aumentan la detección del objetivo, pero el seguimiento presenta muchos cambios de identidad. No es un modelo promovido a producción.')
p('Abrir index.html para los videos y las matrices a resolución completa. El paquete conserva resultados negativos y separa explícitamente evaluación, predicción y verdad sintética.',True)

page('1. Qué pregunta responde la campaña')
p('La campaña anterior mostró una debilidad de escala: entrenar sobre vistas predominantemente lejanas y después recortarlas no aporta el detalle óptico de una cámara realmente cercana. Por instrucción del usuario se canceló aquella campaña de vuelos y se inició un dataset con nuevas posiciones de cámara.')
h('Qué se mantuvo fijo')
p('Se conservaron los arbustos aprobados V142/V181, sin plántulas geométricas en la base, y el generador, las hojas, ramas, materiales, suelo, cielo y vecinos. La variación autorizada fue la cámara: distancia, azimut y elevación. Esta campaña no es otra búsqueda estética ni un barrido de colisiones.')
h('Cadena de trabajo')
table([['Etapa','Entrada y salida','Situación'],['Generación','Estructura morfológica congelada → RGB y máscaras raster originales.','Terminada'],['Aprendizaje','Parches train + aumentación nativa → peso nuevo.','Terminado'],['Evaluación estática','Dos pesos, mismas vistas completas, mismo preprocesado.','Auditada'],['Vuelos','Tres trayectorias nuevas → inferencia, IDs y matrices.','Evaluados'],['Localización','Marcador decodificado + movimiento relativo ruidoso → estimación métrica.','Pendiente']], [90,315,90])
h('Tres conceptos que no deben mezclarse')
p('<b>Segmentación:</b> asignar una máscara y clase al capacho en una imagen. <b>Seguimiento:</b> mantener la identidad del mismo objeto entre imágenes. <b>Localización 3D:</b> estimar su posición métrica respecto de un marco. Una buena máscara aislada no garantiza identidad estable ni exactitud 3D.')
p('Las clases pintona, madura y sobremadura describen la <b>apariencia del capacho</b>. No son una validación de la madurez interna del fruto. Blender interpreta la estructura morfológica; no sustituye su fuente de verdad.',True)

page('2. Dataset multiescala y prevención de fugas')
table([['Partición','Fuentes / semillas','Vistas','Parches'],['Train','C01-C04 / 814200-814203','192','1152'],['Validación','C06-C07 / 814205-814206','96','576'],['Prueba de desarrollo','C09-C10 / 814208-814209','96','Vistas completas']], [100,250,65,80])
p('Cada planta se observa a 1,2 / 2,2 / 3,6 m del punto de mira, en ocho azimuts y dos elevaciones. Las imágenes son de 1280 × 720. Estas distancias no son la separación de todos los vecinos ni la distancia mínima al follaje.')
p('La separación se hace por JSON fuente y semilla antes de crear poses, vecinos clonados, recortes o aumentaciones. Todos los derivados heredan el split de origen. No se incorporaron imágenes mixtas de la campaña cancelada. Las semillas reservadas 914140-914145 permanecen intactas.')
img('dataset_sample/val_near_mediano_mask.png',max_height=146)
img('dataset_sample/val_far_mediano_mask.png',max_height=146)
p('Ejemplos de validación cercano y lejano: RGB completo con supervisión original superpuesta. Cian: pintona; amarillo: madura; violeta: sobremadura. La galería incluye 18 vistas train/val, seleccionadas por cobertura de tamaños y no por rendimiento del modelo.',True)
p('<b>Límite:</b> hay topología compartida y la prueba fue inspeccionada históricamente. La disjunción de fuentes no convierte este conjunto en un holdout externo de familias independientes. No hay imágenes ni parches totalmente negativos.')

page('3. Cómo se entrenó realmente')
table([['Parámetro','Configuración ejecutada'],['Inicialización','Peso final del piloto congelado: SHA256 79c3dad7…'],['Parches / entrada de red','640 × 640, stride 448; entrada 960. El escalado no crea detalle óptico.'],['Entrenamiento','10 épocas; batch 1; nbs 1; warmup 0; AdamW; lr inicial 0,0002.'],['Carga / memoria','workers 0; threads 4; cache False; plots False; validación batch 1.'],['Aumentación nativa','Ultralytics RandomHSV: h=0, s=0, v=0,1; RandomFlip horizontal p=0,5, solo train.'],['Deshabilitado','Mosaic, mixup, copy-paste y transformaciones afines en este piloto raster.']], [135,360])
p('El adaptador nativo sincroniza imagen, cajas y máscara raster de IDs, preservando componentes desconectados. El cargador histórico ignoraba argumentos de aumentación: esta campaña usa un adaptador verificado mediante llamadas reales. Val y test no reciben aumentación.')
h('Evidencia de aprendizaje, no solo de proceso vivo')
p('Se registraron <b>11.520 lotes y 11.513 actualizaciones reales del optimizador</b>; los parámetros cambiaron en cada época. Se verificaron 11.520 llamadas a RandomHSV y otras tantas a RandomFlip. La ejecución de RandomFlip no significa que todas las imágenes se inviertan: el muestreo usa probabilidad 0,5.')
p('El mínimo de RAM libre superó 14 GiB durante entrenamiento y validación; se conservó la reserva requerida de 2 GiB. El nuevo checkpoint publicado es last.pt, SHA256 9c660824…; no se selecciona un checkpoint por resultados de prueba.')
h('Qué no debe trasladarse a la pose')
p('El flip horizontal se usa para reconocimiento de capachos. No se utiliza para localizar ArUco. Un marcador reflejado no constituye una observación física equivalente para estimar pose.')
p('Fuentes: training_args.yaml, training_results.csv, training_readiness.json y native_augmentation_integration_check.json en evidence/dataset y metrics.',True)

page('4. Qué significan las métricas')
p('<b>Precisión P = TP / (TP + FP)</b>: cuántas predicciones contadas son correctas. <b>Recall R = TP / (TP + FN)</b>: cuántos capachos verdaderos se recuperan. <b>F1 = 2PR / (P + R)</b>: balance entre ambos. Una máscara se empareja por solapamiento IoU y la clase debe coincidir para contar un acierto.')
p('En vistas completas y vuelos se congelaron confianza 0,25 e IoU de máscara 0,5. Una clase incorrecta afecta FP y FN. No tener pareja espacial puede significar ausencia de propuesta o máscara con IoU insuficiente; no demuestra que el objeto fuera invisible.')
p('<b>AP</b> resume la curva precisión-recall al variar el corte de confianza; <b>mAP50</b> promedia AP entre clases a IoU 0,50. <b>mAP50-95</b> promedia además umbrales IoU 0,50 a 0,95 en pasos de 0,05. Es más exigente con la forma de la máscara.')
rows=[['Época 10, validación por parches','P','R','mAP50','mAP50-95']]
for title,suffix in [('Máscaras','M'),('Cajas','B')]:
    rows.append([title]+[pct(float(epoch[f'metrics/{key}({suffix})'])) for key in ['precision','recall','mAP50','mAP50-95']])
table(rows,[195,75,75,75,75])
p('<b>Estos mAP corresponden exclusivamente a los 576 parches de validación del entrenador.</b> No son mAP de vuelos ni de vistas completas. Sus P/R no representan necesariamente el mismo punto de confianza del evaluador nativo. No hay mAP completo de vuelos calculado en este corte.')
h('Todos frente a elegibles')
p('Se reporta siempre el conjunto completo y un subconjunto con al menos 100 píxeles de máscara visible y lado mínimo de caja de 8 píxeles en la imagen original. Es una heurística de ingeniería para estudiar tamaño, no un límite universal de YOLO. Su F1 debe leerse junto a la fracción de objetos que cubre.')
p('El área de máscara visible no es una tasa de oclusión. El subconjunto elegible no debe ocultar la dificultad del resto de objetos ni justificar por sí solo promoción científica.',True)

page('5. Comparación en vistas completas')
p('Referencia y modelo multiescala reciben exactamente las mismas vistas val/test y máscaras raster originales. Ambos usan parches exhaustivos de 640, stride 448 y entrada 960. No hay ROI seleccionada con verdad, HSV en inferencia ni adaptación de decisiones con prueba.')
rows=[['Partición / alcance','Modelo','P','R','F1']]
for split,label in [('val','Validación'),('test','Desarrollo')]:
    for scope,slabel in [('all','todos'),('eligible','elegibles')]:
        for model,mlabel in [('reference','Referencia'),('new','Multiescala')]:
            x=static['models'][model][split]['all_distances'][scope]
            rows.append([label+' / '+slabel,mlabel,pct(x['precision']),pct(x['recall']),pct(x['f1'])])
table(rows,[160,100,78,78,79])
p('En prueba de desarrollo, F1 global sube <b>8,52 puntos porcentuales</b>. El recall nuevo es 49,57%: todavía se omite o clasifica mal aproximadamente la mitad de las observaciones bajo esta regla. El F1 elegible 76,98% cubre solo 9.036 de 23.175 observaciones (38,99%).')
table([['Modelo nuevo, desarrollo','Cerca','Intermedia','Lejos'],['F1, todos los tamaños','64,86%','62,13%','54,73%']], [225,90,90,90])
p('Se conservan resultados negativos: cae la precisión en casos lejanos/elegibles. La confusión madura → pintona aumenta de 172 a 297, aunque pintona → madura baja de 838 a 538. Esto impide afirmar que la separación de transición quedó resuelta.')
p('Las cifras nuevas no son directamente comparables con las históricas de parches 384 y ROI heurística. Esta comparación controla el preprocesado entre los dos pesos actuales. Fuente completa: metrics/static_full_views.json.',True)

page('6. Diseño de los tres vuelos nuevos')
table([['Ruta','Frames / total','Inspección','Tránsito'],['Legacy','178 / 44,50 s','10,00 s','32,75 s'],['Vertical','167 / 41,75 s','8,50 s','31,50 s'],['Órbita parcial','282 / 70,50 s','21,25 s','47,50 s']], [120,145,115,115])
p('Todas las rutas muestrean a 4 fps. Los totales ya incluyen 1,75 s de adquisición/retorno por ruta, además de inspección y tránsito. Los presupuestos y las vistas difieren: no es una comparación de estrategias a igual duración.')
img('images/routes.png',max_height=265)
p('<b>Legacy:</b> recorrido por ambas caras manteniendo la planta completa proyectada. <b>Vertical:</b> cuatro barridos dentro del follaje real, C06 y C07 por frente/reverso, con inclinación de cámara para la banda baja. <b>Órbita:</b> solo sectores transitables, 180° en C06 y 225° en C07; no se logró una vuelta de 360°.')
p('El preflight revisó 9.886 obstáculos evaluados, continuidad, proyección y margen conservador. Los sectores bloqueados por plantas, postes, cuerdas o columnas de acceso se conservaron. El tránsito puede ir por el extremo exterior y a 1,978 m de altura. No se movieron plantas para acomodar el vuelo.')
p('La cobertura geométrica acumulada 99,78-100% de los barridos no garantiza visibilidad de cada fruto ni mide oclusión. Solo existe un ArUco8 frontal común; C07 no tiene marcador propio.',True)

page('7. Detección e identidad durante inspección')
rows=[['Objetivo C06/C07','Legacy','Vertical','Órbita parcial']]
ins={r:routes[r]['by_phase']['inspection_'+r] for r in routes}
for title,scope,key in [('Precisión, todos','target_all','precision'),('Recall, todos','target_all','recall'),('F1, todos','target_all','f1'),('Precisión, elegibles','target_eligible','precision'),('Recall, elegibles','target_eligible','recall'),('F1, elegibles','target_eligible','f1')]:
    rows.append([title]+[pct(ins[r]['detection'][scope][key]) for r in routes])
rows.append(['Fracción elegible','36,85%','80,51%','80,93%'])
table(rows,[210,95,95,95])
p('Los acercamientos aumentan la proporción de observaciones con tamaño elegible. La órbita no mejora F1 frente al vertical en estas observaciones, pese a dedicar más tiempo a inspección. No se puede aislar causalmente solo el efecto de distancia con rutas y duraciones distintas.')
rows=[['Seguimiento de elegibles','Legacy','Vertical','Órbita parcial']]
rows.append(['Cambios ID / pares emparejados']+[f"{ins[r]['tracking']['target_eligible']['adjacent_identity_switches']} / {ins[r]['tracking']['target_eligible']['adjacent_both_matched_pairs']}" for r in routes])
rows.append(['Tasa condicional de cambios']+[pct(ins[r]['tracking']['target_eligible']['conditional_adjacent_switch_rate']) for r in routes])
rows.append(['Cobertura de pares consecutivos']+[pct(ins[r]['tracking']['target_eligible']['consecutive_match_coverage']) for r in routes])
table(rows,[210,95,95,95])
p('<b>El seguimiento sigue siendo una limitación grave.</b> La tasa cuenta cambios de track entre pares adyacentes que el evaluador logra emparejar espacialmente en ambos fotogramas. No es IDF1, HOTA ni MOTA, y no evalúa reidentificación después de huecos.')
p('Los FP exclusivos del objetivo se atribuyen aproximadamente por centroide dentro de su envolvente visible. El matching global se hace primero y no se rematchea de forma favorable. Esta región pertenece al evaluador privado, no a una selección automática del estimador.',True)

for route,label,frame in [('legacy','Legacy',104),('vertical','Barrido vertical',15),('orbit','Órbita parcial',163)]:
    page('8. '+label+': matrices y caso difícil')
    p('Inspección del objetivo actual C06/C07. Izquierda: todos los tamaños. Derecha: elegibles (100 píxeles y lado mínimo 8). Filas: verdad; columnas: predicción. La última fila/columna representa predicciones u observaciones sin pareja.',True)
    row=[]
    for scope in ['target_all','target_eligible']:
        file=ROOT/f'matrices/{route}/confusion_phase_inspection_{route}_{scope}.png'
        image_width,image_height=PILImage.open(file).size
        row.append(Image(str(file),width=242,height=242*image_height/image_width))
    story.append(Table([row],colWidths=[247.5,247.5]))
    story.append(Spacer(1,10))
    img(f'images/{route}_worst_{frame:03d}.jpg',max_height=260)
    x=selection['selected'][route]['worst']
    m=x['metrics']
    p(f'Caso de menor F1 de inspección según regla predeclarada: frame {frame}, objetivo {x["target"]}, cara {x["side"]}. TP {m["tp"]}, FP {m["fp"]}, FN {m["fn"]}; F1 {pct(m["f1"])}. El HTML incluye también el caso mediano y el mejor, conservando la imagen completa.',True)
    if route=='legacy':
        p('En las vistas alejadas muchos capachos quedan pequeños. El alto recall del subconjunto elegible no describe el 63,15% restante de observaciones de inspección. No atribuir cada omisión a tamaño sin comprobar la correspondencia individual.')
    elif route=='vertical':
        p('Acercarse mejora F1 total, pero no elimina confusiones ni fragmentación temporal. En esta ruta corregida la cámara recorre bandas de follaje; que una banda salga del encuadre no es el fallo de overshoot del fragmento antiguo.')
    else:
        p('En inspección orbital quedan 2.149 observaciones objetivo sin pareja espacial y 359 clases incorrectas; entre elegibles, 934 y 325. Hojas, fragmentos de silueta y bordes aparecen en las muestras; son observaciones visuales, no causas individuales demostradas.')

page('9. Negativos que deben conservarse')
table([['Hallazgo','Evidencia','Interpretación permitida'],['Transición de clase','Madura → pintona: 172 a 297 en desarrollo.','El nuevo entrenamiento no resuelve todas las confusiones.'],['Identidad inestable','Replay CPU idéntico al baseline; 27 de 32 cambios elegibles por competencia involucraron tracks antiguos.','La competencia antigua es una hipótesis causal plausible, no una corrección probada.'],['Costura de parches','Caso con silueta dividida en x=640.','Puede fragmentar una instancia; no demuestra que explique todos los errores.'],['Piloto vertical antiguo','C06 pasó de 96 a 10 capachos visibles al elevar cámara y punto de mira fuera del follaje.','Fallo demostrado de cámara; no atribuirlo al detector.'],['Recuadro externo','En los dos videos completos la escena y el proxy se ven pequeños.','Útil como contexto espacial; limitada legibilidad del movimiento fino.']], [115,190,190])
p('La receta futura del barrido se corrigió mediante un único preflight conjunto. El fragmento negativo no se sustituyó: está incluido en videos/negative_pilot_vertical_presentation_v1.mp4. Legacy conserva también sus versiones v1 y v2 de presentación; v2 corrige únicamente el recorte del proxy del observador.')
p('Los videos completos legacy y vertical se decodificaron íntegros (178 y 167 frames, H264, 4 fps). Se revisaron inicio, mitad, final y las transiciones predeclaradas. Las máscaras e IDs son las mismas salidas evaluadas; el observador y el proxy no alimentan la inferencia.')
p('Una entrega parcial no oculta estos negativos ni autoriza variar el tracker, los pesos o los umbrales. La investigación posterior debe plantear experimentos acotados y predeclarados, sin seleccionar decisiones con test.')

page('10. Pose y localización 3D: estado real')
p('<b>No hay una estimación métrica 3D nueva ejecutada y evaluada para las tres rutas completas en este corte.</b> Se han preparado sensores relativos y decodificado marcadores; eso no es todavía precisión de pose de cámara ni localización de capachos.')
table([['Componente','Estado / alcance'],['ArUco','ID8 común frontal. Lado codificado 0,20 m; marco 0,2667 m. No son 10 cm.'],['Decodificación RGB real','Legacy 80/178; vertical 30/167; órbita 43/282. Son conteos de frames, no cobertura de triangulación.'],['Sensores relativos','Incrementos cada 0,25 s. Ruido heurístico de 2,5 mm y 1 mrad por incremento; sin calibración física, sesgo ni deriva correlacionada.'],['Estimador permitido','RGB, tiempos, intrínsecos, dimensiones físicas y movimiento relativo ruidoso.'],['Solo evaluador privado','Poses exactas, verdad 3D, máscaras, identidades verdaderas y perturbaciones muestreadas.']], [135,360])
h('Condiciones del siguiente paso')
p('Usar solo marcadores realmente decodificados y pasar marker_side_m=0.20 explícitamente. Conservar marker_id al construir observaciones. No reutilizar el valor histórico por defecto de 0,10 m ni el intervalo antiguo de 0,5 s. No relajar los filtros de paralaje o error de reproyección para aumentar artificialmente la cobertura.')
p('El fallo histórico audit_pose_reprojection_v1 omitía marker_id. Una versión posterior reparó la interfaz, pero su fusión 0/32 no acredita exactitud. Esa revisión está conservada y no se reabre la cola antigua.')
h('Qué debe contener la entrega final')
p('Errores de posición y, si se estima, orientación de cámara; error de localización de capachos; cobertura sobre oportunidades válidas; número de rechazos y motivos. Un resultado de cobertura nula debe informarse como tal. Las identidades inestables son un riesgo para asociar observaciones de triangulación.')

page('11. Cómo apropiarse del material')
table([['Archivo / carpeta del paquete','Uso recomendado'],['guia_estudiantes.pdf','Lectura metodológica y límites del corte.'],['index.html','Comparación portable: videos, matrices y vistas completas. Descargar el directorio; GitHub no ejecuta HTML como una web.'],['dataset_sample/','18 ejemplos completos train/val con máscaras originales y selección documentada.'],['metrics/','Resultados de entrenamiento, comparación estática y agregados de las tres rutas.'],['evidence/','Protocolos, manifiestos, auditorías y JSON completos de vuelos comprimidos sin pérdida. Contiene información privada de evaluación: no usar como entrada del estimador.'],['models/','Peso multiescala y referencia exacta, vinculados por SHA256.'],['source_snapshot/','Lectura de las implementaciones efectivamente usadas. Incluyen dependencias y rutas históricas; no constituyen un pipeline autónomo listo para lanzar.'],['videos/','Dos rutas completas PiP y cuatro clips de diagnóstico conservados.']], [140,355])
h('Primera sesión de trabajo propuesta')
p('1. Leer las definiciones de las páginas 5-6 y reproducir P/R/F1 de una matriz. 2. Ver legacy y vertical, separando adquisición, inspección y tránsito. 3. Contrastar el peor, mediano y mejor caso con la matriz de su ruta. 4. Registrar dudas como evidencia observada o hipótesis, manteniendo la distinción.')
p('Para verificar el paquete, ejecutar <b>python verify_package.py</b> desde este directorio: usa solo la biblioteca estándar y compara tamaños/SHA256. Para explorar una evaluación completa: descomprimir evidence/flights/*_full_evaluation.json.gz; el JSON compacto conserva métricas y omite listas largas de cambios de IDs.')
p('Este repositorio publica resultados y ejemplos, no una copia completa de las 384 imágenes, 627 capturas y todas las cachés de predicciones. Sus hashes/manifiestos y evaluaciones están incluidos; los datos masivos permanecen en outputs del equipo de origen. No relanzar render ni entrenamiento para leer esta entrega.',True)

page('12. Trazabilidad, límites y cierre pendiente')
h('Fuentes de las cifras')
p('<b>Datos y aprendizaje:</b> evidence/dataset/protocol.json, split_plan.json, split_integrity_audit_v1.json, training_readiness.json, native_augmentation_integration_check.json; metrics/training_results.csv. La auditoría de separación pasó 868.156 comprobaciones; la de entrega estática, 166.846 comprobaciones y 768 recomputaciones CPU.')
p('<b>Vuelos:</b> evidence/flights/protocol.json, preflight_delivery_v1.json, example_selection.json y los recibos de cada ruta. Las auditorías aritméticas pasaron 284.009 / 266.543 / 459.377 comprobaciones para legacy / vertical / órbita. Los JSON originales se preservan comprimidos sin pérdida.')
p('<b>Identidad y pose:</b> evidence/diagnosis/tracking_failure_diagnosis_v1.json y historical_reprojection_recovery_review_v1.json. El informe cronológico completo está en evidence/context/dataset_multiescala_2026-10-20.md.')
h('Identidades de artefactos')
for label,value in [('Modelo nuevo','9c660824319f2c436321d2545cf9b267348c7be64d7780a396d8382555eb05cd'),('Referencia','79c3dad74e7cf9caab3c82a3e37ea72235352568d7dfacbd5c9e8284cb190073'),('Protocolo de vuelos','86dabc5a22a59aa53207547e565bd9408a05e3dac8c47df037d11aff71b78026')]:
    p(f'<b>{label} SHA256</b><br/>{value[:32]}<br/>{value[32:]}',True)
h('Condiciones de uso e interpretación')
p('Resultados exclusivamente sintéticos, con topología compartida, test de desarrollo inspeccionado, ausencia de negativos completos y ruido de sensores idealizado. No se ha probado transferencia a campo real, navegación autónoma segura ni madurez interna del fruto. Las métricas condicionales y la decodificación ArUco no bastan para promoción.')
p('El código propio conserva la licencia del repositorio; esta publicación no relicencia pesos ni componentes de terceros. Los checkpoints derivados de Ultralytics conservan las obligaciones de su origen. Consultar LICENSE y los avisos de dependencias antes de redistribuirlos fuera del equipo.')
p('El cierre requiere el tercer video PiP revisado, la ejecución y evaluación 3D con cobertura y rechazos, y un informe final consistente. La publicación final será una nueva versión; este corte parcial y los negativos permanecerán disponibles.')


def footer(c,doc):
    c.saveState()
    c.setStrokeColor(colors.HexColor('#b9cdce'));c.line(50,43,545,43)
    c.setFont('Guide',8);c.setFillColor(colors.HexColor('#42555e'))
    c.drawString(50,29,'UCHUVA  /  Campaña multiescala  /  Entrega parcial 21-10-2026')
    c.drawRightString(545,29,str(doc.page))
    c.restoreState()


doc=SimpleDocTemplate(str(ROOT/'guia_estudiantes.pdf'),pagesize=(595.28,841.89),leftMargin=50,rightMargin=50,topMargin=44,bottomMargin=57,title='Campaña multiescala de uchuvas: guía de resultados parciales',author='SyntheticPlantGeneration - documentación del experimento')
doc.build(story,onFirstPage=footer,onLaterPages=footer)
(ROOT/'guia_contenido.txt').write_text('\n\n'.join(outline),encoding='utf-8')
print(ROOT/'guia_estudiantes.pdf')
