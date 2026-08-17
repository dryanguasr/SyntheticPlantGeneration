# Mejoras virtuales prioritarias para el generador v2

Fecha de corte: 2026-08-14.

## Resumen ejecutivo

La iteración v2 reemplaza tres fuentes de aleatoriedad visual poco defendibles
por modelos reproducibles: cohortes fenológicas ordenadas, maduración conjunta
del capacho y mezcla de cámaras calibrada contra `train` real. También sustituye
el tapete verde uniforme por un sotobosque procedural estratificado y añade un
diagnóstico del detector que separa detección ausente de mala localización.

La implementación es deliberadamente compatible: `legacy_independent` y el
fondo histórico continúan disponibles para ablaciones, mientras que el pipeline
del dataset declara explícitamente `literature_cohort_v1` y
`layered_understory_v2`. No se usaron píxeles del dataset real para crear
texturas y no se consultó el `test` real.

El arbusto disponible se trató únicamente como referencia cualitativa. Los
presupuestos de nodos, densidad de ramas y cobertura de fondo permanecen como
hipótesis de ingeniería hasta contar con mediciones de cultivo.

## Cambios implementados

### Fenología y arquitectura

- Esquema morfológico `1.2`, aditivo y compatible con JSON anteriores.
- Modelo puro y serializable `literature_cohort_v1` con DAA estimado, BBCH,
  cohorte, rango ontogenético, procedencia e incertidumbre.
- Edad topológica: órganos antiguos tienden a madurez y los distales a flor o
  fruto joven; se permiten transiciones vecinas, no inversiones mayores.
- Primera bifurcación entre 8--12 nodos.
- El prior térmico de Salazar queda registrado como diagnóstico; no genera
  nodos. El preset visual usa 16--17 nodos principales para conservar una copa
  útil tras la bifurcación, marcado como `manual_initial_guess`.

### Maduración del capacho

- Continuo `inflated_green` → `transitioning_yellow` → `straw_yellow` →
  `dry_deteriorated`.
- Color, textura, turgencia, inflación, área relativa, circularidad,
  pubescencia, asimetría y pliegues dependen del mismo progreso.
- Prior localizado 45--90 DAA: área relativa aproximada `1,00 → 0,86` y
  circularidad `0,59 → 0,39`.
- Biblioteca procedural `0.5.0` con 14 conjuntos y selección condicionada por
  madurez.
- Eliminación de la segunda contracción por estado y de macroondas periódicas.
  Los capachos permanecen cerrados, el fruto oculto y la clase única es
  `calyx`.

### Fondo y composición

- Perfil `layered_understory_v2`: suelo PBR CC0 existente, parches de pasto,
  kikuyo, malezas, follaje y hojarasca irregular a varias escalas y planos de
  profundidad.
- Variación tonal por macolla y grupo, sin descargar activos nuevos.
- Proxy `non_calyx_scene_context` fuera de cajas expandidas 10 %, con
  luminancia, saturación, dispersión tonal y energía de borde.
- No se aplicó corrección global de luminancia; el antecedente redujo el
  mAP50--95 aproximadamente `0,0156`.
- Calibración determinista de cámaras contra `train` real: 0 % contexto,
  36 % plano medio y 64 % acercamiento. La predicción previa al render tiene
  brecha media de `4,562` puntos porcentuales y máxima de `6,843`.

## Verificación previa al piloto

- 104 pruebas unitarias y de integración ligera: todas pasan.
- Auditoría pura de 100 semillas (`14000--14099`): válida, con cero fallos del
  contrato crítico, cero inversiones fenológicas mayores y bifurcación siempre
  entre 8--12 nodos. Los avisos generales de competencia y proximidad se
  conservan como diagnóstico; no se ocultaron ni se interpretaron como
  colisiones físicas Blender.
- 12 comparaciones v1/v2 pareadas en semilla, cámara, iluminación y exposición:
  aceptadas con EEVEE y cero pasadas Cycles. La densidad se corrigió después de
  que una primera versión revelara copas demasiado ralas.
- El `.blend` representativo está disponible junto a las comparaciones densas.

## Diagnóstico multisemilla del detector

Se analizaron solamente las 133 imágenes reales de `val` con los tres
checkpoints baseline y los tres híbridos seleccionados, usando confianza 0,25
y emparejamiento IoU determinista. El `test` real no se abrió.

| Semilla | Δ TP IoU ≥0,75 | Δ FN ausente | Δ FP de fondo | Lectura |
|---:|---:|---:|---:|---|
| 20260811 | +30 | -30 | +1 | mejora clara de recall/localización |
| 20260812 | +27 | -16 | -5 | mejora consistente |
| 20260813 | -5 | +4 | -12 | menos FP, pero leve regresión en TP/FN |

La señal es favorable en dos de tres semillas, pero heterogénea. Es evidencia
exploratoria, no prueba de significancia ni justificación para abrir `test`.
Los archivos por detección permiten continuar el análisis por área, borde,
orientación, carga de objetos, luminancia y error relativo de centro/tamaño.

Agregando las tres semillas para localizar la brecha de AP75, la tasa de TP
`IoU≥0,75` pasa de 38,4 % a 46,3 % en cajas menores al 1 %, de 72,8 % a 75,7 %
en cajas de 1--5 % y de 92,3 % a 94,7 % en cajas mayores al 5 %. El principal
cuello de botella sigue siendo, por tanto, el objeto pequeño. En imágenes con
6--10 objetos la tasa sube de 62,5 % a 67,7 %, y con más de 10 objetos solo de
49,4 % a 51,9 %. Los contactos con borde mejoran de 69,2 % a 74,6 %. Esto
prioriza escala, escenas cargadas y truncamiento sobre una corrección global de
color.

## Piloto de 60 imágenes

El piloto se generó con semilla `16000`, EEVEE normal, una sola instancia de
Blender, `cycles_qa_count=0`, reserva mínima de 4 GB de RAM y reanudación. La
ejecución produjo 60 imágenes, 151 cajas y splits 48/6/6. Se aceptaron 38 tomas
`real_close` y 22 `real_mid`; 40 candidatos quedaron rechazados y documentados.

| Criterio | Umbral | Resultado |
|---|---:|---:|
| Colisiones, capachos abiertos o fruto oculto visible | 0 | **0; cumple** |
| Brecha máxima de bandas de área | ≤7 pp | **7,384; no cumple** |
| Brecha media de composición | ≤3 pp | **1,899; cumple** |
| Energía de borde contextual mediana | ≥30 | **14,815; no cumple** |
| Dispersión contextual de luminancia mediana | ≥38 | **27,449; no cumple** |
| Luminancia frente a v1 | no inferior por más de 2 niveles | **+10,547; cumple** |
| Macroondulaciones o brillo plástico nuevo | ausentes | **cumple** |

La auditoría de archivos también cumple: no hay ausencias, hashes repetidos
entre splits, desajustes etiqueta/manifiesto ni clases distintas de `calyx`.
La mezcla general de composición es cercana, pero la distribución de área
conserva 19,205 % de cajas menores al 1 % frente a 14,023 % reales, 43,709 %
entre 1--5 % frente a 51,093 %, y 37,086 % mayores al 5 % frente a 34,884 %.

## Rediagnóstico posterior al piloto

El fondo v2 aumentó la luminancia contextual mediana de 103,711 a 115,158 y la
luminancia global de 104,441 a 114,988 frente a v1. Sin embargo, no añadió la
frecuencia espacial buscada: la energía de borde pasó apenas de 14,387 a
14,815 y la dispersión contextual bajó levemente de 27,600 a 27,449. Con el
mismo proxy, `train` real mide 36,156 y 52,175, respectivamente.

La causa probable no es falta de cantidad de objetos procedurales sino su
representación en píxeles:

- grandes planos de suelo y fondo quedan suavizados por distancia y enfoque;
- muchas briznas son subpíxel y no aportan bordes estables;
- las malezas de hoja ancha repiten siluetas lisas, colores de rango estrecho y
  orientación de tarjeta, por lo que pueden leerse planas o flotantes;
- el material del suelo forma parches amplios y de baja frecuencia; su mezcla
  multiescala no se tradujo en suficiente microcontraste a resolución final;
- la calibración de cámaras provino del rendimiento morfológico v1. V2 cambió
  densidad, tamaños y aceptación, y desplazó cajas desde la banda media hacia
  las bandas pequeña y grande.

La revisión visual sí confirma capachos mates, cerrados y sin macroondas nuevas.
También confirma que el residuo sintético dominante está en follaje y malezas,
no en el brillo del capacho. Por tanto no sería correcto intentar arreglar el
resultado con una corrección global de color.

### Acciones virtuales recomendadas antes del próximo piloto

1. Crear una pequeña matriz cruzada de calibración v2 con presencia explícita
   de `real_context`, `real_mid` y `real_close`; el piloto actual no contiene
   `real_context`, por lo que no permite reestimar limpiamente las tres filas de
   rendimiento.
2. Recalibrar la mezcla con rendimientos v2 y fijar una penalización específica
   a cajas menores al 1 %, buscando recuperar la banda 1--5 %.
3. Sustituir las tarjetas lisas de maleza por pocas familias de malla curvada,
   con pecíolo, nervio, contacto verificable con suelo y siluetas irregulares.
4. Aumentar microvariación y discontinuidades del suelo en espacio de cámara:
   UV/escala, hojarasca fina, suelo expuesto y oclusiones pequeñas, sin usar
   píxeles reales ni cambiar la luminancia global.
5. Ajustar grosor y densidad proyectada de pastos para que sobrevivan al
   muestreo final, en lugar de incrementar solo el número de hebras subpíxel.
6. Ejecutar primero un micropiloto estratificado de 12--18 escenas y exigir los
   dos umbrales contextuales antes de repetir un piloto de 60.

## Limitaciones que se mantienen

- La distribución de arquitectura y carga reproductiva no representa todavía
  una población cultivada medida.
- El fondo gana profundidad, pero continúa siendo procedural; no sustituye un
  inventario local de cobertura, especies, alturas y hojarasca.
- La rugosidad, pubescencia y respuesta angular del capacho son aproximaciones
  visuales, no BRDF ni perfiles físicos medidos.
- Las comparaciones pareadas fijan la cámara histórica, pero al cambiar la
  ontología fenológica el mismo órgano no siempre existe en ambos árboles; son
  comparaciones visuales de escena, no correspondencia órgano a órgano.
- Tres semillas del detector permiten observar consistencia, no establecer
  significancia estadística definitiva.

## Mediciones prioritarias cuando exista acceso al cultivo

1. Fotografías RAW con carta de color, escala y vistas multiángulo por estado.
2. Seguimiento desde antesis a 45/60/75/90 días.
3. Longitud, diámetro, área proyectada, circularidad, costillas, pliegues y
   pubescencia.
4. Altura, anchura, nodos, entrenudos y orientación foliar por estrato.
5. Poda, ramas conducidas, tutorado, separación y altura de alambres.
6. Cobertura y altura de kikuyo, *Lolium*, otras malezas, suelo y hojarasca.
7. Política experta para objetos pequeños, truncados y ocluidos.
8. Holdout real virgen en otras filas, fechas y condiciones.

Hasta entonces, las observaciones del arbusto aislado permanecen
`to_be_measured` o referencia cualitativa.

## Artefactos

- `outputs/calibration/virtual_fidelity_v2/composition_calibration.json`
- `outputs/audits/literature_cohort_v1_100_seeds/audit_report.json`
- `outputs/comparisons/virtual_fidelity_v1_v2_pairs_dense/`
- `outputs/comparisons/virtual_fidelity_v1_v2_pairs_dense/representative_v2.blend`
- `outputs/diagnostics/detector_real_val_multiseed_v2/`
- `outputs/datasets/uchuva_virtual_fidelity_v2_pilot_seed_16000/`
- `outputs/current_review/uchuva_virtual_fidelity_v2_pilot_seed_16000.blend`
- `outputs/audits/virtual_fidelity_v2_pilot_seed_16000/`

## Decisión de escalado

Estado actual: **piloto rechazado para escalado**. Cumplen integridad,
morfología, luminancia, composición media y revisión del capacho; fallan la
brecha máxima de área y, con margen amplio, los dos criterios contextuales. No
se generará el lote de 640 ni se iniciarán nuevos entrenamientos. La siguiente
ejecución recomendada es un micropiloto de fondo y cámaras, no un dataset ni un
experimento de entrenamiento.
