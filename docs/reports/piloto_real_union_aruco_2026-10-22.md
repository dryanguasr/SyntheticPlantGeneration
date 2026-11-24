# Piloto real depurado y ArUco — 22 de octubre de 2026

## Resultado y alcance

Se completó la preparación del dataset, el entrenamiento y la evaluación técnica. Los resultados de detección cuantitativos corresponden a la prueba real agrupada de desarrollo; los videos nuevos no tienen anotaciones exhaustivas, por lo que no se informa AP externo. La salida respecto a ArUco contiene desplazamientos en imagen, no posiciones 3D ni exactitud métrica validada.

## Datos y procedencia

Fuente local: `union_anotadas_20261021_local_v1`, exportación `latest` preservada por hash; no se certificó identidad con la v1 publicada en Ultralytics. Originales conservados. Se excluyeron 22 imágenes completas por 25 polígonos y se separaron ocho copias exactas. Quedaron 643 imágenes, con grupos por prefijo de secuencia, duplicados y unión conservadora de candidatos dHash; fotografías sin grupo verificable se restringieron a entrenamiento. La independencia por sesión no está demostrada.

| Split | Imágenes | Pintona | Madura | Sobremadura |
|---|---:|---:|---:|---:|
| train | 461 | 3601 | 759 | 363 |
| val | 88 | 900 | 143 | 64 |
| test | 94 | 806 | 91 | 58 |

Las proporciones resultantes son 71,70/13,69/14,62 %, con desviaciones de +1,70/−1,31/−0,38 puntos frente a 70/15/15. Se priorizó mantener grupos indivisibles y las tres clases. Las 251 fotografías sin secuencia verificable quedaron en entrenamiento; validación y test contienen secuencias identificadas por nombre, sin afirmar independencia por sesión. `group_split_summary.json` conserva los prefijos y componentes.

Los tres videos y el Excel se copiaron a `inputs/` con SHA-256, sin editar las fuentes. El CSV y la galería `review/` dejan decisiones pendientes para Karen y Caroline; no se enviaron mensajes.

## Entrenamiento y controles

Inicialización común `yolo26n.pt`; semilla 20261022; entrada 960; batch 2; AdamW LR 0,0002, nbs=2 y sin warmup. Aumentación nativa: HSV solo valor 0,1 y reflejo horizontal 0,5. Sin mosaic, mixup, copy-paste, traslación, escala aleatoria, rotación ni perspectiva. Se verificaron las transformaciones nativas y su ausencia en validación, así como cambios de parámetros y pasos efectivos del optimizador.

| Brazo | Épocas registradas | Pasos efectivos | Segundos | SHA-256 best |
|---|---:|---:|---:|---|
| real | 20 | 4615 | 1441.6 | `684281d2c20153045b92c5fc81869cf3e6ce0ec4e99887a2208e21be62c00a09` |
| mixed | 20 | 4615 | 1112.3 | `f52137f603879814f80fc7cd1a58b9cc7f84a688330032299ec709e563aeeea8` |

La mezcla usa 384 imágenes reales y 96 sintéticas (80/20 por imágenes), todas las sintéticas proceden de las vistas train existentes con semillas 814200–814203. Se comprobaron IDs raster, número de píxeles y cajas contra máscaras nativas. Instancias reales: 3828; sintéticas: 14003. La exposición por instancia no es 80/20 y hay menos exposición real que en real-only. Las clases sintéticas siguen siendo aproximaciones de apariencia; no hay madurez agronómica medida. No se generaron renders.

Presupuesto de pasos emparejado: **True**. Los checkpoints se seleccionaron por validación bajo la misma política; pueden corresponder a épocas diferentes.

## Detección en prueba agrupada

Confianza común 0.248248, seleccionada solo con F1 medio de validación del brazo real; matching IoU 0,5, entrada 960 y configuración de inferencia común. AP se calcula con barrido de confianza. Se preservan por separado localización colapsada y clasificación.

| Brazo | AP50–95 macro | AP50 | AP50–95 colapsado | Precisión micro fija | Recall micro fijo |
|---|---:|---:|---:|---:|---:|
| real | 0.1865 | 0.2442 | 0.4299 | 0.4358 | 0.6251 |
| mixed | 0.1806 | 0.2343 | 0.3921 | 0.5120 | 0.5361 |

| Brazo | Clase | AP50–95 | AP50 | Precisión fija | Recall fijo |
|---|---|---:|---:|---:|---:|
| real | Pintona | 0.4033 | 0.5267 | 0.4731 | 0.6973 |
| real | Madura | 0.0743 | 0.1008 | 0.1667 | 0.2857 |
| real | Sobremadura | 0.0820 | 0.1050 | 0.3462 | 0.1552 |
| mixed | Pintona | 0.3731 | 0.4878 | 0.5538 | 0.6067 |
| mixed | Madura | 0.0821 | 0.1072 | 0.2167 | 0.1429 |
| mixed | Sobremadura | 0.0864 | 0.1080 | 0.1754 | 0.1724 |

Variación mezcla − real: **-0.0059 AP50–95** (-0.59 puntos porcentuales). Es un piloto de una semilla y una partición; no demuestra significancia estadística ni transferencia a sesiones independientes. No se reajustaron modelos después de consultar test.

**La mezcla no mejoró AP50–95 macro en este piloto.** Se conserva como resultado negativo; no se promueve el brazo sintético como reemplazo del detector real.

## Videos, ArUco y referencias manuales

Se procesaron los tres videos completos a 5 fps, con índices de frame y timestamps originales. Los IDs de tracking se asignan por IoU y expiran tras un segundo; sus duraciones son descriptivas, no métricas MOTA/IDF1. Los candidatos ArUco se filtran por tamaño, convexidad y degeneración. Las esquinas pueden propagarse por flujo óptico durante un máximo de un segundo con control bidireccional, siempre marcado como propagado. Esta inspección técnica de marcadores utilizó los propios videos y no constituye validación externa del estimador de pose.

| Video | Frames a 5 fps | Referencia observada | Observada o propagada | Detecciones real | Detecciones mixto |
|---|---:|---:|---:|---:|---:|
| 125180 | 929 | 56 | 60 | 1224 | 714 |
| 125181 | 502 | 26 | 26 | 842 | 376 |
| 125182 | 536 | 2 | 2 | 567 | 392 |

| Brazo | Video | Tracks | Mediana de observaciones/track | Tracks con ≥5 observaciones |
|---|---|---:|---:|---:|
| real | 125180 | 985 | 1.0 | 16 |
| real | 125181 | 719 | 1.0 | 5 |
| real | 125182 | 459 | 1.0 | 6 |
| mixed | 125180 | 546 | 1.0 | 11 |
| mixed | 125181 | 318 | 1.0 | 2 |
| mixed | 125182 | 321 | 1.0 | 3 |

Los conteos son observaciones por frame, **no frutos únicos ni aciertos**. La cobertura de ArUco corresponde al detector y sus filtros; no certifica precisión de IDs contra anotación humana exhaustiva. Un número mayor de detecciones no demuestra mejora. Cada predicción contiene desplazamiento X derecha/Y arriba respecto a los centros de marcadores visibles, en píxeles y normalizado por su tamaño aparente. Z permanece ausente. No se infiere pertenencia botánica al marcador por cercanía.

Inspección cualitativa del agente: en `125180` y `125181` a 19,79 s, y en `125182` a 59,79 s, se observan capachos visibles sin caja y cajas sobre zonas foliares. Las vistas amplias y las referencias parcialmente recortadas son casos difíciles conservados en los videos. Esta revisión es puntual, no anotación humana exhaustiva ni una medida de recall externo.

Se preservaron las celdas del Excel y 32 referencias XYZ del bloque N:Q de Hoja 2, con unidades cm confirmadas por el usuario. Los demás bloques siguen disponibles íntegros en `workbook_cells.json`. M0/M1 son resultados históricos, no predicciones de este piloto. No se reutilizaron los porcentajes de precisión del libro ni se sustituyeron ausencias por cero. El archivo `fruit_identity_review.csv` deja pendientes la correspondencia visual de cada fruto, video/timestamp y origen.

La convención solicitada es X derecha, Y arriba, Z hacia adentro. No se estimó una transformación física válida: el origen no está confirmado, falta calibración de cámara y el lado negro del ArUco no se conoce. A4 no fija ese lado; las hojas observadas presentan curvatura, oclusión o recortes, por lo que no se promovió una escala fiable. El contrato de signos conserva Z hacia adentro y cambia el signo de Y respecto a una cámara derecha/abajo/adelante; esa conversión tiene determinante −1 y no es una rotación de pose. Se probó la conversión de desplazamientos de metros a centímetros como fixture, sin aplicarla a coordenadas 3D inexistentes. **No hay errores XYZ en centímetros ni error de reproyección de pose disponible.** Incluso con pose métrica del marcador, el centro de una caja en una sola imagen no fija la profundidad del fruto; no se asumió que los frutos sean coplanares con la hoja. No se asociaron frutos minimizando distancia contra la verdad manual.

## Entrega y continuidad

- `dataset/`: imágenes y cajas depuradas; `manifest.json` y `readiness.json`: procedencia y controles.
- `review/`: CSV de duplicados, imágenes excluidas y revisión de polígonos con recortes.
- `training/<brazo>/weights/best.pt`: pesos seleccionados; `completion.json`, configuración y evidencia del optimizador.
- `evaluation/`: AP por clase/colapsado, matrices y predicciones con umbral congelado.
- `videos/`: observaciones por frame, tracking, referencias observadas/propagadas y videos individuales.
- `delivery/`: tres videos comparativos (real a la izquierda, mixto a la derecha cuando existe) e índice HTML.
- `references/`: Excel extraído y lista de identidades por confirmar.

Pruebas específicas: diez pruebas aprobadas, incluidas las ocho del piloto sobre cajas, particiones, aumentación nativa, ejes y unidades, referencias ausentes, rechazo de marcadores degenerados y separación entre localización/clasificación, más dos de auditoría. El validador del grafo conserva los diez localizadores preexistentes rotos; no se presenta como exitoso ni se modificaron cambios ajenos. No se instalaron dependencias ni se publicaron cambios.

Siguiente paso: adjudicar polígonos e identidades con Karen y Caroline, medir el cuadrado negro y calibrar la cámara; después fijar el origen físico y reconstruir con correspondencias multivista o profundidad medida, para evaluar métricamente sin usar las coordenadas verdaderas como entrada del estimador.

Cierre UTC: 2026-10-22T05:55:24.898638+00:00
