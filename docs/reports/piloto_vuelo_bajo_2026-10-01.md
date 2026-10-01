# Piloto de vuelo bajo con ArUcos — 2026-10-01

## Resultado del ensayo

Ejecución completa: **sí**. Validación posterior: **aprobada**.
Duración: 273.16 s simulados; 1690.3 s de ejecución.
Se conservaron las 36 plantas y los 2.280 capachos originales; el inventario objetivo
de `plant_12` a `plant_23` contiene **747 capachos**.

| Etapa | Capachos únicos |
|---|---:|
| Existentes objetivo | 747 |
| Visibles en observaciones evaluadas, ≥16 px | 645 |
| Detectados correctamente | 12 |
| Con posición planar | 4 |
| Con posición 3D asociable | 0 |
| Visibles únicamente por debajo de 16 px | 1 |

Precisión agregada: **61.11 %**. Recall por observación:
**0.04 %**. Cobertura de capachos únicos visibles:
**1.86 %**.
Son métricas del escenario sintético, no del desempeño en videos reales.

## Vuelo y validez de captura

Cuatro pasadas, a 0,65 y 0,95 m por ambas caras del pasillo central. Giros y
cambios de altura en x = ±4,6 m, fuera del cultivo. Cámara ideal de 1280 × 720,
90° horizontales y 20° hacia abajo; RGB y segmentación coincidentes a 15 Hz.
Evaluación a 5 Hz mediante exposiciones originales de sello idéntico.

- Error máximo de altura durante pasadas: **1.40 cm**.
- Velocidad máxima durante pasadas: **0.1541 m/s**.
- Cota conservadora de separación ejecutada: **20.37 cm**.
- Pares sincronizados: **1367**; pares faltantes: **0**.
- Comprobaciones de identidad/proyección: **272735/272735**.
- Intervalo máximo entre poses de telemetría: **0.068 s**.

El arranque suspendido del modelo tiene un transitorio de motores fuera del
cultivo. Se registra, pero no se incluye en las pasadas: el avance empieza al
recuperar la altura. La velocidad de ese transitorio no se presenta como la de
inspección: el máximo de toda la telemetría, incluido el arranque, es
**0.1899 m/s**. El techo de 0,20 m/s se cumple también en la inicialización medida.
Las cotas se basan en superficies completas, esfera envolvente,
poses observadas y corrección temporal; no en ausencia de contactos.

La primera configuración, conservada en `outputs/gazebo/low_pilot_v1`, tuvo
dos pruebas técnicas descartadas (sincronización y arranque) y un ensayo
abortado a 41,82 s por deriva lateral. El monitor se activó al llegar a una
cota de 16,0 cm. Se corrigió la realimentación transversal, se repitió la prueba
de 10 s y se congeló `low_pilot_v2`. Esa ejecución se interrumpió a 244,562 s
por agotamiento de memoria al grabar. Se preservaron 3.706 pares RGB/máscara.
En `low_pilot_v3` se separaron los catálogos de materiales: se verificaron
2.280 mallas y materiales idénticos, sin alterar SDF, inventario ni misión.
También se sincronizó el comando de sustentación antes de despausar la física;
la prueba técnica anterior a esa sincronización se conserva como fallida.
Tras otra prueba de 10 s, se congelaron código, geometría, materiales y detector.
No se retiraron obstáculos ni se modificó el aspecto del cultivo para mejorar resultados.

## Detección

Se evaluaron **1255** imágenes; se separaron
112 imágenes de arranque/transición o sin máscara.
Coincidencias verdaderas objetivo: 22; falsos positivos sin
correspondencia: 14; falsos negativos: 49312;
duplicados: 3. Coincidencias correctas ajenas a las doce
plantas objetivo: 0, separadas de la métrica objetivo.

| Pasada | Imágenes | TP | FP sin correspondencia | FN | Precisión | Recall |
|---|---:|---:|---:|---:|---:|---:|
| pass_0 | 313 | 1 | 3 | 9412 | 25.00 % | 0.01 % |
| pass_1 | 314 | 8 | 6 | 15428 | 57.14 % | 0.05 % |
| pass_2 | 314 | 7 | 3 | 9995 | 70.00 % | 0.07 % |
| pass_3 | 314 | 6 | 2 | 14477 | 75.00 % | 0.04 % |

| Planta | Existentes | Visibles | Detectados | Planar | 3D |
|---|---:|---:|---:|---:|---:|
| plant_12 | 65 | 58 | 0 | 0 | 0 |
| plant_13 | 42 | 35 | 2 | 0 | 0 |
| plant_14 | 65 | 61 | 4 | 1 | 0 |
| plant_15 | 65 | 57 | 0 | 0 | 0 |
| plant_16 | 55 | 49 | 0 | 0 | 0 |
| plant_17 | 65 | 65 | 0 | 0 | 0 |
| plant_18 | 65 | 49 | 2 | 1 | 0 |
| plant_19 | 65 | 46 | 1 | 1 | 0 |
| plant_20 | 65 | 59 | 0 | 0 | 0 |
| plant_21 | 65 | 52 | 1 | 0 | 0 |
| plant_22 | 65 | 53 | 0 | 0 | 0 |
| plant_23 | 65 | 61 | 2 | 1 | 0 |

La precisión por planta queda **no disponible**: los FP sin correspondencia no
tienen identidad de planta. No se asignaron arbitrariamente para fabricar una
métrica. `plants.csv` incluye recall y conteos por planta; `frames.csv` y
`passes.csv` conservan los FP. En `inventory.csv`, los indicadores de cobertura
se interpretan solo en filas `target=true`; las demás identifican el contexto.

## Localización

ArUcos observados en **99.20 %** de las
imágenes evaluadas. Diccionario `DICT_4X4_100`, lado negro de 10 cm.

| Método | Estimaciones evaluadas | Mediana | RMSE | P90 | ≤2 cm | ≤5 cm | ≤10 cm |
|---|---:|---:|---:|---:|---:|---:|---:|
| Planar X/Y | 19 | 28.19 cm | 69.90 cm | 96.05 cm | 15.79 % | 26.32 % | 42.11 % |
| 3D por capacho único | 0 | no disponible | no disponible | no disponible | no disponible | no disponible | no disponible |

La homografía entrega X/Y sobre el plano del marcador, con profundidad
desconocida; su error no es un error 3D. La cobertura planar respecto al
inventario es 0.54 %;
la cobertura 3D es 0.00 %.
Las estimaciones sin posición permanecen en los denominadores de cobertura.
Las 19 estimaciones planares son combinaciones detección/marcador, no
capachos distintos; incluyen referencias lejanas. El video muestra la referencia
válida más cercana en píxeles para facilitar su lectura, sin elegir por error verdadero.

IPPE usa solo esquinas observadas y escala métrica. Cada reconstrucción conserva
el marco de su marcador. Se exigen ≥3 observaciones, paralaje ≥3°, profundidad
positiva y reproyección ≤3 px. Rechazos registrados:
`{"fewer_than_three_observations": 14}`.
El flujo óptico y la asociación uno a uno rechazan correspondencias ambiguas.

Las posiciones verdaderas del marcador se usan solo al evaluar o dibujar el
mapa mundial. El estimador se ejecutó con el paquete RGB, sellos, calibración y
dimensiones del ArUco, sin máscaras, inventario ni odometría de Gazebo.

## Congelación y archivos

Pasaron 33 pruebas de software: transformaciones, escala, triangulación con
posición conocida, falta de paralaje, marcador ausente, asociaciones ambiguas,
oclusión, conteo sin duplicados, corrección lateral y catálogos de materiales.
Los tres MP4 finales pasaron decodificación completa y tienen 1280 × 720 a 15 fps.
Los videos anotados repiten exposiciones de 5 Hz solo para presentación;
esas repeticiones no se cuentan como observaciones.

- Modelo: `natural_hybrid_alpha_045`, clase capacho, confianza 0,25, letterbox
  640², end-to-end sin NMS adicional. SHA-256: `19b6de32788952d77ee842cd4a1d5895212cf6f7b90d7c441f31357c392be4ca`.
- `experiment_lock.json`: hashes de código, SDF, configuración y detector.
- `outputs/gazebo/low_pilot_v3/flight/vuelo_bajo.mp4`: vuelo con cámara de seguimiento y vista frontal.
- `outputs/gazebo/low_pilot_v3/flight/vuelo_anotado.mp4`: detecciones y posiciones estimadas; 3D posterior.
- `outputs/gazebo/low_pilot_v3/flight/evaluation/comparacion_verdad.mp4`: TP, FP y FN contra máscaras.
- `position_map.png`: mapa mundial de verdad y estimaciones 3D; transformación
  mundial exclusivamente del evaluador.
- `planar_marker_maps.png`: mapas planares independientes por ArUco, cuando hay estimaciones.
- CSV por imagen, planta, pasada, tamaño visible y altura; coordenadas/error
  planar y 3D en sus tablas correspondientes.
- `observations.jsonl`, `reconstructions.jsonl`, `association_rejections.jsonl`
  y `associations.jsonl`: observaciones, decisiones y unión posterior con verdad.

La visibilidad se estratifica por píxeles observables; no es una fracción de
oclusión. La referencia espacial es el centro de la geometría original,
distinto en general del centro de su caja visible. No se evalúa madurez.
No hubo reentrenamiento, RGB-D ni ajustes retrospectivos de textura o umbral.
Las salidas pesadas permanecen locales e ignoradas por Git.
