# Segunda revisión: color, ramificación y pose foliar

La primera propuesta fue rechazada por el usuario: colores demasiado pálidos y
arbustos demasiado simples, conservando una valoración positiva de las hojas del
suelo. Se ejecutaron **50 imágenes de segunda ronda y cuatro comprobaciones de
pose separadas**. No hay aprobación humana, banco admitido ni entrenamiento nuevo.
Las imágenes anteriores, perfiles, fuentes y resultados se conservaron.

Galería: `outputs/appearance_factorial_20261026/calibration/round_02/review/index.html`.
Incluye referencias reales sin recoloración, ilustración aportada, comparaciones
focales, B/L/T/LT contextuales, arquitectura antes/después y prueba de pose.

## Color y luz

No se aplicó saturación uniforme a todas las clases. En la primera ronda Madura
tenía una saturación mediana 0,289 frente a 0,400 en entrenamiento; Pintona ya
estaba más saturada que la mediana real, pero oscura. Los multiplicadores lineales
de albedo pasan a [0,90; 1,04; 0,52], [1,24; 1,12; 0,48] y [1,28; 1,04; 0,48].
El mayor cambio relativo corresponde a Madura. Se conserva textura fina, rugosidad,
ausencia de emisión y desgaste separado de clase. Sobremadura no implica marrón
oscuro ni deterioro. La exposición sigue en EV 0; se ajustan ambiente, sol y relleno.

| Clase | Saturación real mediana | Candidata ronda 1, difusa | Candidata ronda 2, difusa | Luminancia ronda 2 |
|---|---:|---:|---:|---:|
| Pintona | 0,446 | 0,535 | 0,515 | 0,471 |
| Madura | 0,400 | 0,289 | 0,424 | 0,543 |
| Sobremadura | 0,393 | 0,413 | 0,509 | 0,488 |

Son medidas de píxeles RGB codificados, no reflectancias. Cambió también el
ejemplar focal, por lo que las diferencias entre rondas no son una ablación causal
pura de materiales. Dentro de cada ronda sí se conserva geometría/cámara entre
B/L/T/LT. Sobremadura ahora supera más la mediana de saturación real: requiere
juicio visual, no puede declararse mejor solo por ser más viva. La ilustración
NTC 4580 aportada sigue siendo cualitativa; no transforma etiquetas de apariencia
del capacho en validación normativa de madurez interna.

La mediana de las medianas del contexto pasó de 0,341 a 0,455 en LT, frente a 0,467
en B de la segunda ronda. La primera y segunda ronda tienen plantas diferentes;
la comparación es descriptiva. Se conservan semillas, perfiles y geometría de
vegetación del suelo, y no se han descargado assets ni instalado dependencias.

## Por qué los arbustos parecían simples

V2 extendió el eje principal, pero conservó laterales de 3–5 nodos con presupuestos
de longitud cortos. V3 desarrolla 20 nodos principales y laterales de 6–8, con
presupuestos diferenciados por orden. Se compararon alternativas antes de elegir
esta hipótesis adulta intermedia. No cambian tamaños individuales, probabilidades
axilares ni la bifurcación heredada; no se prescribe cantidad de hojas o frutos.

| Semilla | Ejes v2 → v3 | Hojas v2 → v3 | Frutos v2 → v3 |
|---|---:|---:|---:|
| 2026102600 | 7 → 27 | 35 → 145 | 8 → 37 |
| 2026102601 | 15 → 42 | 65 → 212 | 14 → 61 |
| 2026102602 | 14 → 31 | 65 → 161 | 16 → 33 |
| 2026102603 | 4 → 29 | 27 → 161 | 3 → 53 |

La inspección del render mostró que aumentar nodos no bastaba: numerosas láminas
estaban casi horizontales y se veían de canto desde la cámara. La pose v4 prueba
un rango 30–80° relativo al eje local con el marco ortogonal existente, manteniendo
idénticos los órganos, dimensiones, estados y extracciones aleatorias de v3.
Es una hipótesis de postura no medida, no una rotación para mirar a la cámara.

Cuatro vistas LT adicionales preservan cámara e intrínsecos de v3; la diferencia
numérica máxima de matrices reserializadas es 1e-7. Se observa más superficie
foliar, pero la corrección es moderada: todavía no demuestra semejanza suficiente
con arbustos reales. Las cámaras no se elevaron para ocultar el problema. No se
promete que más hojas o mayor saturación produzcan mejor AP.

## Geometría y continuación

Los cuatro árboles v3 tienen cero errores de integridad morfológica, pero sus
auditorías de malla detectan 32/72/37/48 intersecciones y 31/71/50/45 violaciones
de separación. Con pose v4: 35/63/40/47 y 21/38/27/36, respectivamente. Estas
auditorías diagnósticas usan `tolerate_only_leaf_leaf=false`; el banco declara
aparte su excepción de ocupación blanda hoja–hoja. Persisten contactos cáliz–tallo
y otros fallos que no pueden llamarse oclusión visual ni descartarse por conveniencia.

La evidencia permite revisar colores y forma, **no admitir estas escenas para
entrenar**. El siguiente requisito técnico es corregir las poses con restricciones
nodales y parámetros efectivos y repetir la auditoría, sin quitar frutos ni
sobrescribir intentos. La revisión humana tampoco sustituye esa verificación.

Las fuentes del piloto anterior y las 50 capturas originales se verifican por
hash. El informe de verificación de esta revisión registra pruebas CPU, contratos,
presupuesto activo y los diez errores preexistentes del grafo, sin nuevas
regresiones. Solo después de revisión visual y admisión física se podrá congelar
la configuración del banco. No se ha iniciado la matriz de entrenamiento.

La ejecución conjunta final pasó **93 pruebas CPU**. Los cuatro árboles v4 se
revalidaron después del render con el contrato explícito de pose: cero errores
de integridad y advertencias de plausibilidad conservadas. Los 13 archivos
congelados y el informe del piloto cerrado siguen intactos. El grafo mantiene
sus diez errores preexistentes y ninguna regresión nueva. El ledger acumula
596,9 segundos activos en cuatro trabajos: dos imágenes de prueba inicial,
50 de primera ronda, 50 de segunda y cuatro comprobaciones técnicas de pose
(106 imágenes en total, no 106 muestras de entrenamiento).
