# Piloto de cultivo disperso, doble anotación y ArUco

El preset `sparse_overhead_strings_v1` conserva la morfología nodal y compone
cuatro escenas de seis hileras por seis plantas. La revisión densa produce doce vistas
por escena: cercana, media y lejana a media altura del arbusto objetivo y a
40 cm del suelo, desde el frente y desde atrás del mismo arbusto objetivo.
Son 48 imágenes: cuatro escenas por doce vistas. La altura usada para el
dron es el máximo Z de los ejes del arbusto, reportado por el intérprete
como proxy de altura; no es una medición de la silueta foliar. El valor
ejecutado queda registrado por captura.
No es un experimento de transferencia ni una validación agronómica.

## Supuestos y escala

La relación heredada es 0,08 unidades Blender por centímetro: **8 unidades por
metro**, con `scene.unit_settings.scale_length = 0.125`. El terreno local es
plano. Separación entre plantas 1,4 m, entre hileras 1,8 m, cable a 2,5 m;
alargamiento inicial de ejes 1,4 y ángulo lateral limitado a 55 grados.
Son `manual_initial_guess`, no mediciones del cultivo. Los órganos no se
desvinculan de sus nodos. La papa es una representación contextual de hojas
compuestas, sin afirmación de simbiosis ni modelo de crecimiento.

La revisión usa `sparse_overhead_dense_crown_v2`, derivado de una copia del
preset histórico, con más ramificación nodal y hojas mayores. Las referencias
visuales de train y sus hashes quedan en `config.json`; no se usan fotos de test
para ajustar la apariencia. El contraste de 144 plantas registra 4,24 veces
más hojas y 3,34 veces más ejes que v4.

El solver se aplica por planta durante ocho iteraciones; omite la búsqueda
exhaustiva posterior de poses y lo declara como `not_run_iterative_preview`.
La pose foliar mantiene la heurística de inserción de 110 a 155 grados.
La auditoría posterior de mallas abarca la escena completa. Los contactos
intencionales del tutorado se distinguen de colisiones físicas y oclusiones.
Un reporte con advertencias no se convierte en aprobación física. Los cruces
de mallas foliares se registran como ocupación blanda geométrica, nunca como
oclusiones visuales ni como contacto físico validado. La auditoría de mallas
no mide oclusión en imagen.

## Etiquetado

El objeto es exclusivamente el **capacho visible**, sin pedicelo, baya ni hojas.
Cada instancia tiene un grado sintético explícito (0–6), conservado en JSON:

| YOLO | Nombre | Grados | COCO |
|---|---|---|---|
| 0 | verde | 0–1 | 1 |
| 1 | pintona | 2–4 | 2 |
| 2 | madura | 5 | 3 |
| 3 | sobremadura | 6 | 4 |

La agrupación procede del usuario; «sobremadura = 6» es una aproximación del
experimento, no una equivalencia normativa verificada ni deterioro obligatorio.
`Nuevo Dataset/Norma.webp` es referencia cualitativa aportada por el usuario,
con SHA-256 en configuración; no sustituye al texto íntegro de NTC 4580 ni a
una medición colorimétrica. El [anteproyecto del Codex publicado por FAO](https://www.fao.org/4/x1702s/x1702s0s.htm)
distingue color del cáliz de madurez del fruto. `agronomic_maturity` permanece
desconocida y `human_validation` pendiente.

De una máscara maestra por RGB se derivan cajas YOLO, cajas COCO y segmentación
de instancias COCO RLE sin compresión. El RLE recorre columnas y conserva huecos
y componentes desconectados. No se rellenan partes ocultas. Se exige un mínimo
compartido de 24 píxeles visibles y cajas de 6 × 6 píxeles; las exclusiones se
registran y la máscara maestra se conserva. La paleta admite hasta 4095 IDs
distintos y falla explícitamente fuera de ese límite.
La versión de paleta queda registrada; el generador histórico rechaza reanudar
configuraciones anteriores sin esta versión para evitar mezclar máscaras.

El RGB usa EEVEE; la identidad se rasteriza en Workbench plano sin antialiasing,
con fondo transparente convertido explícitamente a ID 0. Así se evitan mezclas
de colores que puedan confundirse con otras instancias. La verificación de
proyección contrasta cada caja visible con los límites geométricos del capacho
en Blender; complementa la igualdad píxel a píxel, que por sí sola no detecta
una máscara maestra incorrecta.

Los archivos COCO comparten IDs, clases, áreas y cajas. La exportación monoclase
derivada asigna `calyx = 0` a todas las instancias retenidas. Los originales
históricos no se modifican. El piloto no asigna splits automáticamente:
`scene_id` es el grupo indivisible para una futura campaña.

## ArUco y coordenadas

Cada planta tiene una placa frontal y posterior, orientadas a pasillos opuestos.
Se usa `DICT_4X4_100`: IDs `2*i` y `2*i+1`, con `i` por fila y columna. Son 72
IDs únicos por escena, identificados globalmente mediante escena e ID. El lado
negro mide 10 cm, margen blanco 2 cm y borde inferior de placa a 5 cm del suelo.

Las coordenadas se exportan en metros: mundo Z arriba; cámara OpenCV X derecha,
Y abajo y Z adelante; marcador X derecha, Y arriba, Z hacia fuera. Se incluyen
intrínsecos ideales, distorsión nula, transformaciones y esquinas. Los centros
de capacho son centros de sus cajas geométricas locales transformados al mundo;
no centros de cajas 2D ni estimaciones obtenidas por el detector.

La pose se calcula con IPPE Square, conservando soluciones alternativas con
profundidad positiva y eligiendo por reproyección, nunca por ground truth.
La proximidad de errores de reproyección inferior a 0,25 px se registra como
ambigüedad heurística. No detectar un marcador proyectado no demuestra un
fallo: puede estar ocluido o ser demasiado pequeño. Se exportan referencias
3D de cada capacho respecto a **ambas** placas de su planta, sin reconstrucción
de profundidad del fruto desde RGB.

PC y Android permiten seleccionar 50 o 100 códigos. El predeterminado histórico
sigue siendo `DICT_4X4_50`; para este piloto seleccionar `DICT_4X4_100` y confirmar
10 cm de lado. Las aplicaciones mantienen su estimación planar; el evaluador
calibrado 3D del piloto es una herramienta independiente.

## Ejecución y artefactos

Usar un directorio nuevo en cada intento; se rechaza sobrescribir escenas o
exportaciones. No se instalan dependencias. Python de entrenamiento ya dispone
de OpenCV y NumPy; Blender aporta su API y BMesh.

```powershell
.venv-training/Scripts/python.exe scripts/prepare_sparse_pilot.py --output outputs/mi_piloto
.venv-training/Scripts/python.exe scripts/run_sparse_pilot.py --root outputs/mi_piloto --scenes 0 --capture-batch
# Tras comprobar los reportes de la primera escena:
.venv-training/Scripts/python.exe scripts/run_sparse_pilot.py --root outputs/mi_piloto --scenes 1 2 3 --capture-batch
& "C:/Program Files/Blender Foundation/Blender 5.1/blender.exe" -b --python scripts/check_sparse_mask_projection.py -- --root outputs/mi_piloto
.venv-training/Scripts/python.exe scripts/export_sparse_pilot.py --root outputs/mi_piloto
.venv-training/Scripts/python.exe scripts/validate_sparse_exports.py --root outputs/mi_piloto
.venv-training/Scripts/python.exe scripts/report_sparse_pilot.py --root outputs/mi_piloto
```

El supervisor usa una sola instancia Blender, lock exclusivo, reserva de RAM
de 4 GiB y techo predeterminado de 1800 s por fase. Construcción, auditoría
y capturas se ejecutan en fases sucesivas para liberar memoria. Con `--capture-batch`,
la escena agrupada se reutiliza para todos los RGB pendientes y después para sus máscaras. Conserva logs, fallos,
tiempos y muestras de memoria. Una ejecución interrumpida conserva sus archivos;
se continúa con `--resume-saved` desde el `.blend` completo, sin mezclar
configuraciones ni sobrescribir fases anteriores. La auditoría conserva solo
128 BVH en memoria y descarta pares cuyas cajas ampliadas están separadas;
La búsqueda de proximidad se limita al mayor umbral relevante de cada par;
las distancias superiores no generaban incidencias. Los umbrales de colisión
y separación permanecen iguales. `--partial` exporta únicamente
capturas terminadas para diagnóstico y las marca como parciales.
Si alguna auditoría física falla, la exportación queda como
`inspection_only_physical_review_required` y `training_eligible=false`.

Cada escena contiene `input.json`, validación morfológica, resolución local,
auditoría de mallas, `.blend`, RGB y máscaras por cámara. `exports/` contiene
detección YOLO (`images/labels`), monoclase, ambos COCO, manifiesto, exclusiones,
evaluación ArUco, superposiciones y hoja de contacto. Los RGB compartidos usan
enlaces duros cuando el sistema lo permite; tratarlos como inmutables.

## Evaluación futura

No entrenar con el piloto como si fuera una muestra estadística suficiente.
Presupuestar una campaña después de inspección visual y física. Comparar
sintéticos nuevos/anterior con información y cómputo equiparados; incluir el
detector real como referencia. El test histórico ya observado permite un
contraste exploratorio de localización colapsando clases. Clasificación por
estado y segmentación reales requieren etiquetas nuevas; no se derivan de
cajas monoclase. Declarar los ArUco y las apariencias nuevas como cambios de
contexto y no atribuir todo efecto a separación o tutorado.

La reserva de RAM es configurable mediante `--min-free-gib` (4 por defecto,
mínimo 2); cada intento registra el valor efectivo. La revisión densa utiliza
2 GiB tras dos paradas documentadas con 4 GiB. Los reintentos conservan logs
y métricas con sufijo de intento, sin sobrescribir los anteriores.
Para las copas densas se conserva `cultivation.blend` como escena de auditoría
y se deriva `capture_geometry.blend`: convierte hojas y tallos evaluados a
malla y los une por planta y clase semántica, conservando UV y materiales.
Los capachos y placas permanecen individuales. No elimina plantas ni órganos.
La copia evita el coste de miles de objetos independientes en EEVEE.
