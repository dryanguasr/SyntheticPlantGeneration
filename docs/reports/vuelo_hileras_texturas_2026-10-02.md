# Vuelo por hileras y prueba de texturas — 2026-10-02

El Neo completó **12/12 caras** con movimiento físico por motores,
sin cambios directos de pose. Se conservaron 36 plantas, 23.385 hojas,
2.340 capachos, ArUcos y tutorado. Las texturas mejoraron modestamente la
detección, pero el desempeño continúa siendo insuficiente.

## Video y recorrido

- [Video completo a 4×, con cámara del dron y vista de seguimiento](../../outputs/gazebo/bouquet_row_flight_batched_v2/flight/vuelo_completo_4x.mp4).
- [Cámara original a velocidad simulada](../../outputs/gazebo/bouquet_row_flight_batched_v2/flight/onboard.mp4).
- [Seguimiento del Neo](../../outputs/gazebo/bouquet_row_flight_batched_v2/flight/chase.mp4).
- [Muestras anotadas a aproximadamente 1 Hz, reproducidas a 4×](../../outputs/gazebo/bouquet_row_flight_batched_v2/flight/annotated_samples_4x.mp4).
- [Recorrido y altura medidos](../../outputs/gazebo/bouquet_row_flight_batched_v2/flight/route.png).

Duración simulada: 994.2 s.
Margen mínimo monitorizado: 0.189 m.
Cota conservadora entre poses ejecutadas, con interpolación lineal: 0.186 m.
Máximo absoluto de roll/pitch: 1.03°.
Velocidad máxima medida entre poses: 0.190 m/s.
Tiempo de ejecución, incluido arranque: 1084.0 s.
Se completaron 35/35 puntos.

La cámara ideal usa 1280×720, 15 fps, 60° horizontales y 15° hacia abajo.
**No reproduce la cámara de fábrica del DJI Neo** ni permite extrapolar estas
distancias a ese hardware. Los pasillos se recorrieron a 0,65 o 0,80 m, a
0,9 m de los ejes de hilera. Los giros se hicieron fuera de X = ±4,8 m.
La distribución sigue siendo 1,4 m entre plantas y 1,8 m entre hileras;
no se recalibró a los aproximadamente 3 m observados por el usuario.

## Comparación controlada de apariencia

24 vistas por variante, mismos puntos y parámetros. RGB y máscaras tienen
sellos simulados idénticos. El IoU de las máscaras entre control PBR y
texturas fue **1.000 en el peor par**.
La rugosidad se mantiene igual en ambos: la diferencia controlada es el albedo.
Cambian tanto el color medio como el detalle espacial; no se aísla el efecto
exclusivo de las nervaduras.
El material anterior sin PBR cambió la cobertura visible y se reporta aparte;
no se usó para afirmar un efecto aislado de textura.

| Variante | Observaciones visibles | Aciertos | FP | FN | Recall |
|---|---:|---:|---:|---:|---:|
| Material anterior (diagnóstico) | 2178 | 3 | 0 | 2175 | 0.138 % |
| Color plano, mismo PBR | 2648 | 2 | 0 | 2646 | 0.076 % |
| Albedo texturizado | 2648 | 10 | 0 | 2638 | 0.378 % |

Son **observaciones por imagen**, con repeticiones entre vistas e incluyendo
plantas de fondo, no capachos únicos. Se usan máscaras con ≥16 píxeles visibles
y coincidencias uno a uno con IoU ≥0,5. No observar FP en sólo 10 detecciones
no demuestra una precisión general del 100 %.

El detector sigue siendo `natural_hybrid_alpha_045`, SHA-256
`19b6de32788952d77ee842cd4a1d5895212cf6f7b90d7c441f31357c392be4ca`. Entrada RGB con letterbox 640×640, confianza 0,25,
salida end-to-end, sin NMS adicional ni reentrenamiento. Las máscaras no se
entregaron al estimador; entraron únicamente en la evaluación posterior.

### Tamaño aparente (análisis descriptivo posterior)

La medida es la raíz del área de la caja visible en el RGB original, no tamaño
físico ni tasa de oclusión. La mayoría de referencias son pequeñas o de fondo.

| Tamaño equivalente (px) | Visibles | Aciertos planos | Aciertos texturizados | Recall texturizado |
|---|---:|---:|---:|---:|
| <16 | 1831 | 0 | 0 | 0.00 % |
| 16-31 | 481 | 0 | 0 | 0.00 % |
| 32-63 | 301 | 1 | 2 | 0.66 % |
| >=64 | 35 | 1 | 8 | 22.86 % |

[Comparación ilustrativa de la vista 10](../../outputs/gazebo/bouquet_row_flight_v1/texture_comparison.jpg).
Se seleccionó porque muestra dos aciertos; los resultados de la tabla incluyen
las 24 vistas, no sólo el ejemplo favorable.

## Detecciones durante el vuelo completo

Se analizaron 942 imágenes RGB originales, con
197 detecciones acumuladas en
160 imágenes. No son objetos únicos
ni aciertos verificados: este video completo no dispone de máscaras de
instancia en la copia agrupada. Las métricas de precisión/recall proceden
exclusivamente de la prueba A/B individualizada.
Los MP4 pueden repetir cuadros para presentación; no se utilizaron esas
repeticiones como observaciones independientes. Las posiciones planares que
guarda el motor de la app no constituyen localización 3D validada en este ensayo.

## Geometría, rendimiento y límites

La malla de inspección tiene 5.824.267 triángulos y conserva 107.159 objetos
geométricos con procedencia. La prueba de silueta de tres plantas dio IoU
0,974–0,979, con menos de 0,6 % de cambio de cobertura frente a la exportación
previa. Para grabar se agruparon exactamente triángulos, UV y normales en
19 materiales; el paquete individualizado quedó preservado para máscaras.

Las mallas completas, sin ese LOD, sirvieron para auditar el recorrido. La
física final usa 36 envolventes conservadoras para los ejes principales:
contienen los cilindros originales, con radio máximo de unos 4,33 cm. Se
volvió a comprobar la trayectoria contra ellas. Se conservan tutorado y
paneles; no se podó ni desactivó un obstáculo para habilitar el vuelo.
El controlador utiliza odometría de Gazebo; no es navegación autónoma con RGB.

Los contactos internos pendientes de v4 siguen pendientes. La prueba no
valida botánica, madurez, fuerzas de cosecha, sensores reales ni transferencia
al cultivo real. La mejora de 2 a 10 aciertos es exploratoria, con muestra
pequeña, y no demuestra significación estadística. Los fallos y la primera
comparación de máscaras no equivalente se conservaron.

## Archivos de evaluación

- [CSV por vista](../../outputs/gazebo/bouquet_row_flight_v1/texture_ab.csv).
- [Métricas A/B y comprobación de máscaras](../../outputs/gazebo/bouquet_row_flight_v1/texture_ab.json).
- [Observaciones JSONL](../../outputs/gazebo/bouquet_row_flight_v1/texture_ab_observations.jsonl).
- [Resumen del vuelo](../../outputs/gazebo/bouquet_row_flight_batched_v2/flight/flight_summary.json).
- [Doce pasadas completadas](../../outputs/gazebo/bouquet_row_flight_batched_v2/flight/completed_passes.csv).
- [Detecciones RGB del vuelo](../../outputs/gazebo/bouquet_row_flight_batched_v2/flight/detections.jsonl).
- [Validación de videos](../../outputs/gazebo/bouquet_row_flight_batched_v2/flight/video_validation.json).

La implementación y los comandos se describen en
[la guía de reproducción](../guides/vuelo_hileras_texturas.md).
