# Registro de evidencia del modelo multi-planta de uchuva

Este registro separa evidencia botánica, mediciones del dataset e hipótesis de
ingeniería. Ninguna entrada etiquetada como `manual_initial_guess`,
`engineering_heuristic` o `to_be_measured` debe describirse como un hecho
botánico validado.

## Taxonomía canónica

- `literature_reported`
- `real_dataset_measured`
- `real_dataset_inferred`
- `manual_initial_guess`
- `engineering_heuristic`
- `implementation_constraint`
- `to_be_measured`

## Parámetros y decisiones activas

| Parámetro o decisión | Valor/rango | Estado epistemológico | Fuente | Implementación | Incertidumbre | Pendiente de validar |
|---|---|---|---|---|---|---|
| Relación nodo–hoja–yema–unidad reproductiva | Un órgano se origina en un nodo o axila | `literature_reported` | Ramírez et al. 2013; modelo morfológico del proyecto | `morphology.py`, `grammar.py` | Media | Sí; revisión botánica local |
| Estados fenológicos simultáneos | Flores y frutos en distintos estados en una planta | `literature_reported` | DOI `10.1016/j.scienta.2013.07.033` | `grammar.py` | Media | No para coexistencia; sí para proporciones |
| Clase de detección | `0 = calyx` | `implementation_constraint` | Contrato vigente del dataset | `yolo_export.py` | Baja | No en esta iteración |
| Capacho cerrado y fruto oculto | `openness = 0`, fruto sin píxeles | `implementation_constraint` | Decisión vigente del proyecto | `parameters.py`, `blender_geometry.py` | Baja | No en esta iteración |
| Entrenudo | 3–8 cm | `manual_initial_guess` | Migración inicial | `parameters.py` | Alta | Sí; medición dimensional |
| Longitud de hoja | 5–11 cm | `manual_initial_guess` | Migración inicial | `parameters.py` | Alta | Sí; medición dimensional |
| Relación ancho/largo de hoja | 0,58–0,86 | `real_dataset_inferred` | Silueta proyectada del dataset original | `parameters.py` | Alta | Sí; perspectiva y escala |
| Órdenes máximos de rama del baseline | 2 | `manual_initial_guess` | Prototipo actual | `parameters.py` | Alta | Sí; arquitectura real |
| Tasa de planta en secado | 8 % | `engineering_heuristic` | Diversidad visual del piloto | `scene.py` | Alta | Sí |
| Tres iteraciones de relajación | 3 | `engineering_heuristic` | Convergencia del prototipo | `cultivation.py` | Alta | Sí; se reemplaza en modo sincronizado |
| Ocho iteraciones de proxies | 8 | `engineering_heuristic` | Calibración geométrica del piloto | `collisions.py` | Alta | Sí |
| Espesor virtual de hoja | Envolvente proxy actual | `engineering_heuristic` | Discretización de geometría Blender | `collisions.py` | Alta | Sí; análisis de sensibilidad |
| Trellis continuo | Postes, líneas y amarres previos al crecimiento | `engineering_heuristic` | Hipótesis de manejo para ablación | `support.py`, `scene.py` | Alta | Sí; contrastar con sistema de cultivo objetivo |
| Crecimiento sincronizado | Propuestas de todas las plantas por paso | `engineering_heuristic` | Měch y Prusinkiewicz 1996; adaptación del proyecto | `growth.py`, `cultivation.py` | Alta | Sí; ablaciones D/E |
| Colonización espacial | Desactivada por defecto | `engineering_heuristic` | Runions et al. 2007, método originalmente evaluado en árboles | `growth.py` | Alta | Sí; solo se conserva si supera la ablación |
| Separación train/val/test real | Train calibra, val evalúa, test queda intacto | `implementation_constraint` | Protocolo de evaluación aprobado | `domain_analysis.py`, diagnósticos | Baja | No |
| Política de contacto por pares | Umbrales configurables de 0–0,024 unidades de escena según el par | `engineering_heuristic` | Envolventes proxy del proyecto | `spatial.py`, `collisions.py` | Alta | Sí; sensibilidad y malla |
| Manifest de referencia | 1.061 etiquetas train, 133 val; 133 test excluidas | `real_dataset_measured` | Lectura 2026-07-23 de `Dataset Original/LABELS` | `scripts/build_dataset_reference_manifest.py` | Baja | Repetir si cambia el dataset |
| Postura foliar | Preferencia 55--86° en crecimiento tutorado; candidatos diarios hasta 94° | `engineering_heuristic` | Observación agronómica de Omar y auditoría proyectiva real/sintética, 2026-08-04 | `grammar.py`, `growth.py`, `light_competition.py` | Alta | Sí; medir inclinación por estrato y hora |
| Deslizamiento tangencial | Candidatos adicionales para orden ≥2 | `engineering_heuristic` | Ablación E | `growth.py` | Alta | Sí |
| Cancelación reproductiva por clearance | La yema queda registrada como `cancelled_hard_clearance`; no se materializa una unidad que invada ocupación dura | `engineering_heuristic` | Regla conservadora de aceptación geométrica | `growth.py` | Alta | Sí; contrastar pérdida de carga reproductiva |
| Competencia lumínica por estratos | Campo compartido bajo/medio/alto con cinco muestras solares y ganancia de cobertura proyectada | `engineering_heuristic` | Observación agronómica de Omar, 2026-07-30; adaptación funcional-estructural del proyecto | `light_competition.py`, `growth.py` | Alta | Sí; medir radiación y cobertura por estrato |
| Tutorado tipo trípode invertido | Expansión radial de cada estrato seguida de guía vertical hacia la línea superior | `engineering_heuristic` | Observación agronómica de Omar, 2026-07-30 | `parameters.py`, `growth.py` | Alta | Sí; medir arquitectura y alturas del tutorado real |
| Mayor densidad foliar tutorada | Incremento moderado de nodos, presupuestos y ramificación; hojas siempre unidas a nodos | `manual_initial_guess` | Observación agronómica de Omar, 2026-07-30 | `parameters.py`, `grammar.py` | Alta | Sí; contar hojas/ejes y medir cobertura real |
| Vegetación acompañante | Mezcla visual `lolium_perenne_like`, `kikuyu_like` y malezas de hoja ancha | `manual_initial_guess` | Observación agronómica de Omar, 2026-07-30 | `blender_environment.py` | Alta | Sí; inventario local y densidad por superficie |
| Fondo verde de cultivo | Terreno verde multiescala, malezas finitas y HDRI agrícola CC0; sin envolvente cilíndrica ni píxeles reales | `manual_initial_guess` | Observación agronómica de Omar y revisión visual 2026-08-04 | `blender_environment.py` | Alta | Sí; comparar frecuencia espacial, cobertura y color con train/val |
| Microseparación hoja–capacho | Elevación acotada 0–4,5 mm conservando el nodo del pecíolo | `engineering_heuristic` | Revisión de oclusiones 2026-07-31 | `collisions.py`, `morphology.py`, `blender_geometry.py` | Alta | Sí; medir separación real y efecto en oclusión |
| Corredor axilar de rama | Los dos primeros entrenudos pueden compartir la zona de unión con el eje padre | `engineering_heuristic` | Corrección de falso conflicto proxy 2026-07-31 | `growth.py` | Alta | Sí; sensibilidad del corredor y auditoría BVH |
| Perfil real para composición | 1.195 imágenes pareadas de train+val; test excluido | `real_dataset_measured` | Medición de solo lectura 2026-07-31 | `domain_analysis.py`, `compare_real_vs_synthetic_domain.py` | Baja | Repetir si cambia el dataset |
| Matriz híbrida | Baseline natural, adición sintética y 75/25, 50/50, 25/75; val/test solo reales | `implementation_constraint` | Protocolo experimental 2026-07-31 | `hybrid_experiments.py` | Baja | Ejecutar con entrenador aprobado |
| Render activo | `standard_eevee`; Cycles desactivado por defecto y disponible por opt-in | `implementation_constraint` | Decisión del usuario, 2026-07-30: coste sin ventaja significativa actual | `scene.py`, `human_validation.py`, pilotos y dataset | Baja | Reevaluar cuando el detalle sea crítico |
| Calibración espacial sintética | Train calibrado: 15.18 % cajas <1 %, 50.00 % entre 1–5 %, 34.82 % ≥5 %; 2.800 objetos/imagen | `real_dataset_measured` | Ajuste reproducible 2026-08-01 contra train+val naturales, sin leer test | `spatial_calibration.py`, `calibrate_synthetic_scale.py` | Media | Repetir al ampliar el dataset sintético |
| Resultado híbrido final | Interpolación 55 % natural / 45 % híbrida: 0.690637 mAP50–95; baseline 0.682706 | `real_dataset_measured` | Test natural fijo, YOLO26n, semilla 20260731, reporte 2026-08-01 | `hybrid_training.py`, `run_checkpoint_interpolation.py` | Alta por una sola semilla y consultas iterativas del test | Confirmar con varias semillas y nuevo holdout |
| Pecíolo de hoja | 0,5–5,5 cm descritos para la especie; presets acotados a 1,2–5,2 cm y tutorado a 2,0–5,2 cm por clearance | `literature_reported` + `manual_initial_guess` | Kew POWO, consulta 2026-08-04; prueba de contacto semilla 0 | `parameters.py` | Media por amplitud interespecífica y ecotipo | Medir ecotipo y estrato del cultivo local |
| Espesor renderizado de hoja | 0,12–0,35 mm | `manual_initial_guess` | Corrección visual 2026-08-04 | `blender_geometry.py` | Alta | Micrómetro por haz/envés, edad y estrato |
| Superficie del capacho v4 | Sin macroonda periódica; 0 pliegues verdes, hasta 1 pajizo y 3 secos, localizados | `engineering_heuristic` | Diagnóstico real/sintético y anatomía publicada; revisión 2026-08-04 | `blender_geometry.py`, `texture_assets.py` | Alta | Separar vena, costilla, pliegue y daño en muestras locales |
| Costillas, intercostales y red del capacho v4.3 | Cresta principal 5,5–8,0 %; valle verde 1,4–2,4 %, pajizo 1,3–2,3 %, seco 1,2–2,1 % del radio local; red albedo más densa y microrrelieve fino | `engineering_heuristic` | Comparación directa con muestras reales 0001, 0042, 0200, 0500 y 0900; revisión 2026-08-04 | `blender_geometry.py`, `texture_assets.py`, `blender_scene.py` | Alta | Fotogrametría, perfiles de sección y BRDF/pubescencia por estado |
| Rugosidad y microrelieve v4 | Roughness Principled 0,93–0,99; normal aplicada 0,22–0,34 | `manual_initial_guess` | Dataset JPEG, límites cualitativos de literatura y diagnóstico visual | `texture_assets.py`, `blender_scene.py` | Alta; no es BRDF medida | Fotografías RAW con carta y serie multiángulo |
| *Lolium perenne* de fondo | Culmos 30–90 cm; láminas 3–20 cm × 2–6 mm | `literature_reported` | Kew POWO/GrassBase, consulta 2026-08-04 | `blender_environment.py` | Media para porte local bajo manejo | Inventario y distribución de altura por cuadrante |
| Kikuyo (*Cenchrus clandestinus*) | Tapete con rizomas/estolones; culmos 3–15(–45) cm; láminas 1–15 cm × 1–5 mm | `literature_reported` | Kew POWO, consulta 2026-08-04 | `blender_environment.py` | Media para porte local | Cobertura, longitud de estolón y frecuencia local |
| Sistema de tutorado de referencia | Espaldera, X, V y vertical están documentados; la geometría local exacta no se presume | `literature_reported` + `to_be_measured` | Lima et al. 2021; Kretzschmar et al. 2012 | `support.py`, `growth.py` | Alta para el predio objetivo | Alturas de alambre, separación, ramas conducidas y poda real |
| Tamaño de dataset sintético v1 | 640 imágenes: 512 train, 64 val y 64 test; una captura por morfología; EEVEE | `implementation_constraint` | Plan aprobado por el usuario, 2026-08-04 | `blender_dataset.py`, CLI de generación | Baja | Auditar manifiesto y validez al finalizar |
| Primera bifurcación v2 | Entre 8--12 nodos; solapamiento permitido entre cohortes fenológicas adyacentes | `literature_reported` + `to_be_measured` | Revisión bibliográfica 2026-08-14; adaptación del proyecto | `phenology.py`, `grammar.py`, `validation.py` | Media para el prior; alta para el cultivo objetivo | Medir arquitectura por planta, manejo y ecotipo |
| Prior térmico de aparición nodal | Temperatura base 6,29 °C; quiebre 1.039,5 °C-día; tasas 0,023 y 0,008 nodos/°C-día | `literature_reported` | Salazar et al. 2008, DOI `10.1590/S0100-29452008000400004` | `phenology.py`; solo diagnóstico | Media | Contrastar clima, ecotipo y manejo del cultivo objetivo |
| Cambio ontogénico localizado del capacho | Entre 45 y 90 DAA: área relativa aproximada 1,00 → 0,86 y circularidad 0,59 → 0,39 | `literature_reported` + `engineering_heuristic` | Diniz et al. 2025, DOI `10.14295/cs.v16.4281`; interpolación del proyecto | `phenology.py`, `blender_geometry.py` | Alta fuera de las condiciones publicadas | Fotografiar y medir cohortes locales a 45/60/75/90 DAA |
| Brecha contextual v1 | Energía de borde mediana real/sintética ≈42,8/17,6; dispersión de luminancia ≈52,1/25,7 | `real_dataset_measured` | Comparación reproducible 2026-08-14, cajas expandidas excluidas | `domain_analysis.py` | Media por el proxy contextual | Repetir con piloto v2 y nuevo holdout |
| Mezcla de cámaras v2 | 0 % contexto, 36 % plano medio, 64 % acercamiento; brecha predicha media 4,562 pp y máxima 6,843 pp | `real_dataset_measured` + `engineering_heuristic` | Búsqueda determinista contra `train` real y manifiesto sintético v1 | `composition_calibration.py`, `composition_calibration.json` | Media; depende del rendimiento morfológico v2 | Verificar sobre piloto v2 y recalibrar si la brecha supera el umbral |
| Diagnóstico detector v2 en `val` | Híbrido mejora TP IoU≥0,75 y FN en 2/3 semillas; la tercera empeora levemente | `real_dataset_measured` | 133 imágenes reales de `val`, seis checkpoints, umbral de confianza 0,25 | `detection_diagnostics.py`, `detection_diagnostic.json` | Alta por tres semillas y un único conjunto de validación | Analizar categorías de error; no consultar `test` |
| Arbusto aislado disponible | Solo referencia visual cualitativa; no define distribuciones del cultivo | `to_be_measured` | Restricción experimental informada por el usuario, 2026-08-14 | Documentación y procedencia de parámetros | Alta | Reemplazar con muestreo de cultivo, cohortes y manejo documentado |
| Piloto de fidelidad virtual v2 | 60 imágenes, 151 cajas, 48/6/6; composición media 1,899 pp; brecha máxima de área 7,384 pp; borde contextual 14,815; dispersión 27,449 | `real_dataset_measured` | Piloto EEVEE semilla 16000 y auditoría 2026-08-14; referencia solo `train` real | `blender_dataset.py`, `domain_analysis.py`, `pilot_audit.json` | Media por tamaño de piloto | Rechazado; mejorar fondo y recalibrar cámaras antes de escalar |

## Reglas de actualización

1. Toda modificación de un rango crítico debe actualizar esta tabla.
2. Una inferencia del dataset debe registrar el procedimiento reproducible.
3. Una fuente bibliográfica debe verificarse en su publicación primaria.
4. Los resultados generados bajo `outputs/` son evidencia experimental, no
   autoridad para definir por sí solos una constante botánica.
