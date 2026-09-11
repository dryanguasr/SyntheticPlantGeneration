# Auditoría científica de generación sintética de uchuva

## Diagnóstico ejecutivo

La recomendación es investigar **generación estructurada que controle la visibilidad y desacople el estado del órgano del contexto, para reducir anotación real en detección multiclase de escenas de cultivo**. La madurez agronómica será un objetivo condicionado a mediciones pareadas del fruto; la apariencia del capacho constituye una observación distinta. La contribución candidata es demostrar cuándo ese control mejora transferencia y eficiencia de etiquetas, mediante intervenciones y ablaciones. Usar Blender o construir un generador de uchuva no constituye por sí solo novedad suficiente.

Está comprobada una base técnica utilizable: módulos morfológicos independientes de Blender, generación de escenas, exportación por instancias y artefactos de entrenamiento recuperables. En esta intervención pasaron las 131 pruebas del baseline Python y las 140 de la suite final, se verificaron los hashes de seis checkpoints del estudio posterior y 180 archivos del piloto v2, y se ejecutó una prueba nueva de máscaras en Blender. Esto demuestra funcionamiento acotado e integridad respecto a los manifiestos; no demuestra realismo botánico poblacional ni mejora científica general.

La señal positiva más publicitada, +0,007930 mAP50–95 por interpolación de checkpoints, proviene de una semilla y un test consultado durante el desarrollo. El estudio posterior de tres semillas, ausente del resumen ejecutivo anterior, deja una señal mucho más débil: **+0,001533 de mAP50–95 medio en el test histórico, con dos de tres deltas negativos**, aunque el recall aumenta en las tres semillas. No existe una confirmación independiente de superioridad sintética. [E2–E4]

No funcionaron la mezcla sintética original, las dosis pequeñas, el ajuste aislado de luminancia ni el cierre natural con la configuración ensayada. El piloto v2 terminó sus archivos pero fue **rechazado para escalado** por distribución de área y estadísticas contextuales. No se debe reinterpretar `dataset_report.status=valid` como aceptación científica: el informe de aceptación es otro artefacto. [E2, E5]

Los bloqueos principales son: ausencia de verdad de terreno multiclase validada, test histórico no independiente, política visible/amodal de cajas reales sin verificar, y falta de una muestra representativa de cultivo con identidad de planta/sesión. No falta Blender ni GPU. La primera intervención ya construyó el contrato de observación, conservó el baseline, corrigió la reanudación y preparó un plan ejecutable. No se entrenó un detector nuevo ni se validó humanamente la maduración.

## Corte, alcance y significado de la evidencia

Inspección realizada el 8 de septiembre de 2026. El conector GitHub devolvió repositorio privado, rama predeterminada `main`, commit **`8fa6ddc8293d403134873a433d6c6fc5a7321dd4`**, fechado el 3 de septiembre de 2026 a las 15:32:31 UTC. Coincidía con HEAD y `origin/main` locales. Se consultaron metadatos, rama, árbol recursivo completo —1.010 entradas, sin truncamiento—, reporte v2 y código de anotación/fenología. No se encontraron incidencias/PR en la búsqueda conjunta; esto no equivale a probar que nunca existieron. Los blobs de `yolo_export.py`, `phenology.py` y `blender_dataset.py` se contrastaron con el árbol remoto. [E1]

Se creó `codex/auditoria-cientifica-blender-20260908`. Había doce archivos rastreados modificados, relativos a Android, su guía, el script de emulador y el grafo, más el reporte Android del 3 de septiembre sin rastrear. Se registraron hashes iniciales y se preservaron los cambios ajenos; las ediciones nuevas del grafo son aditivas salvo una referencia de autoridad corregida. No se hizo push, merge, borrado de datos ni actualización global del entorno.

Los experimentos fechados antes del 16 de agosto no tienen una historia incremental recuperable en Git: `git log -- src/uchuva_lsystem` remite al commit inicial `9e93b12`. Por ello no se asigna un commit experimental exacto a cada ensayo anterior. Se distingue fecha declarada del experimento de fecha de incorporación al repositorio.

Estados utilizados:

| Estado | Alcance |
|---|---|
| **S — estático** | Código, configuración o estructura leídos; no ejecutados por esta auditoría |
| **D — documentado** | Resultado comunicado en un informe histórico |
| **A — artefacto recuperado** | JSON/CSV/log/checkpoint local inspeccionado; no equivale a repetir entrenamiento |
| **R — recomputado/ejecutado** | Operación efectuada ahora, con comando y salida conservados |
| **H — hipótesis** | Explicación o contribución por contrastar |
| **V — validación humana pendiente** | No se ha sustituido por la opinión del agente |

La evidencia experimental ignorada por Git sí existe localmente. Su disponibilidad en este equipo no significa que un clon limpio la incluya. La auditoría no vuelve a evaluar el detector en el test real; lee sus etiquetas y resultados históricos para verificar integridad y procedencia.

## Reconstrucción experimental

### Generador y visualización estructural

El árbol serializable bajo `morphology.py`, la gramática nodal y las interpretaciones Blender/Gazebo mantienen una separación útil. `growth.py`, `support.py`, `spatial.py` y `light_competition.py` agregan restricciones de cultivo y competencia. Su complejidad permite experimentos estructurales, pero no demuestra que la arquitectura generada represente una distribución agronómica medida. La procedencia marca numerosos valores como estimaciones o heurísticas. El prior térmico se registra como diagnóstico, mientras el número de nodos se impone por presupuesto visual. [S; E7]

`literature_cohort_v1` asigna edades, BBCH, DAA y rasgos correlacionados por orden topológico. Las ventanas DAA y las transiciones visuales son una interpolación del proyecto sobre fuentes acotadas; no son un reloj fisiológico validado para el cultivo local. `exposed_fruit` participa en la secuencia fenológica aun cuando el contrato de dataset obliga a capacho cerrado y fruto oculto. Antes de generar etiquetas de fruto debe separarse estado de desarrollo de exposición/daño del cáliz. [S; E7]

El informe del 14 de agosto declara 100 semillas morfológicas, 12 pares visuales y una revisión inicial que produjo copas demasiado ralas. Se conserva como resultado documentado, con artefactos locales identificados; no se repitió esa campaña ni se declararon aprobadas sus revisiones humanas. No apareció `accepted_baseline_manifest.json` bajo `outputs/human_validation`; las diez filas de `photoreal_protocol_v1/human_review.csv` seguían en `pending`. [D, A, V; E5, E8]

### Matriz histórica de mezcla y selección

Configuración documentada: YOLO26n, una clase `calyx`, 640 px, 40 épocas máximas, batch 16, paciencia 10 y semilla de entrenamiento `20260731`; semilla sintética inicial 1000. Dataset sintético original: 100 imágenes, 80/10/10, 368 cajas. Baseline: 1.061 pares reales de entrenamiento; test histórico: 133 imágenes y 480 cajas. La calibración espacial y fotométrica utilizó train+val reales, por lo que esa validación también intervino en decisiones del generador. [D, S; E2]

| Ensayo | mAP50–95 test | Δ natural | Lectura válida |
|---|---:|---:|---|
| Natural completo | 0,682706 | 0 | Referencia de esa semilla/partición |
| +80 sintéticas originales | 0,668219 | −0,014487 | Mezcla perjudicial en este ensayo |
| Presupuesto fijo 75 % real / 25 % sintético | 0,665086 | −0,017620 | Sustituir real no compensó |
| 50 % / 50 % | 0,632931 | −0,049775 | Degradación mayor |
| 25 % / 75 % | 0,618077 | −0,064629 | Degradación mayor |
| +10 / +20 / +40 originales | 0,665880 / 0,666300 / 0,668414 | negativos | Menor dosis no resolvió |
| +80 con luminancia calibrada | 0,667146 | −0,015560 | No respalda corrección global de brillo |
| Preentrenamiento sintético, ajuste real | 0,673291 | −0,009415 | No superó al baseline en esa configuración |
| +80 con escala calibrada | 0,677963 | −0,004743 | Redujo la brecha; no la eliminó |
| +40 con escala calibrada | 0,670448 | −0,012258 | Sin ventaja al bajar dosis |
| Mezcla +80 y cierre natural LR 0,001 | 0,660403 | −0,022303 | Resultado negativo; mecanismo de LR aún inferido |
| Interpolación 55 % natural / 45 % híbrido | 0,690637 | +0,007930 | Ganador exploratorio |

La tabla procede del reporte histórico [D]; el JSON de interpolación confirma el último resultado y la configuración [A]. El coeficiente 0,45 fue elegido entre seis valores mediante validación. El test se utilizó en comparaciones sucesivas del programa de desarrollo; elegir cada checkpoint internamente por validación no restituye su independencia. La precisión pasó de 0,926570 a 0,879691, el recall de 0,843750 a 0,879167 y AP75 prácticamente no cambió. No corresponde llamar al resultado una mejora integral confirmada. [E2]

La escala calibrada alineó distribuciones de cajas, pero comparar épocas iguales con diferente número de imágenes cambia el número de pasos y exposiciones reales. La interpolación necesita además un control de interpolación entre dos modelos **solo reales**, con igual inicialización y presupuesto, para atribuir la mejora a información sintética y no a regularización/ensamble en pesos. Esa atribución no está demostrada.

### Estudio multisemilla posterior recuperado

`hybrid_fidelity_v2_leakage_repaired_20260811` contiene decisión, lock, 15 resultados de validación, resultados finales por semilla y checkpoints. El nombre “v2” se refiere aquí a reparación de particiones; **no es evidencia de entrenamiento con el piloto visual v2 de semilla 16000**. La fuente sintética declarada es `uchuva_synthetic_fidelity_v1_seed_5000`, con 512 imágenes de train. [A; E3]

Se usaron semillas de entrenamiento `20260811`, `20260812`, `20260813`, 40 épocas, paciencia 10, batch 16 y YOLO26n. El `args.yaml` inspeccionado conserva `optimizer=auto`, `deterministic=true`, `pretrained=true`, `workers=4` y aumentaciones online del entrenador; congelar solo el nombre de la arquitectura no basta para reconstruir exposición y política de optimización.

| Adición sintética | mAP50–95 val media | Δ val | Selección |
|---:|---:|---:|---|
| 0 | 0,683909 | 0 | Baseline |
| 56 | 0,686492 | +0,002582 | No alcanzó criterio práctico |
| 118 | 0,691458 | +0,007548 | Seleccionada |
| 265 | 0,692823 | +0,008913 | Dentro de tolerancia respecto al elegido |
| 512 | 0,690213 | +0,006304 | Más dosis sin ventaja suficiente |

El criterio registrado exigía Δ≥0,005, dos semillas positivas y Δrecall≥−0,01; tolerancia 0,002 y desempate por menor dosis. Por eso ganó 118, aunque 265 tenía mayor media. Es una selección explicable por el protocolo, no una contradicción. Fase B quedó condicionada a fracaso de A y no aporta resultados recuperados en esta auditoría. [A; E3]

| Semilla | Δ mAP50–95 test | Δ AP75 test | Δ recall test |
|---:|---:|---:|---:|
| 20260811 | −0,003488 | +0,001679 | +0,016031 |
| 20260812 | +0,008398 | −0,012605 | +0,014894 |
| 20260813 | −0,000312 | −0,005670 | +0,026033 |
| Media | **+0,001533** | **−0,005532** | **+0,018986** |

Estos deltas fueron recalculados ahora a partir de los resultados individuales; los seis archivos de pesos coinciden con sus SHA-256 registrados [R]. La media de mAP pasa de 0,676807 a 0,678339. La desviación estándar de los tres deltas de mAP es 0,006154. Tres inicializaciones no cuantifican incertidumbre entre cultivos o capturas y no justifican una afirmación confirmatoria. El log `hybrid_fidelity_v2_final_test.out.log` corrobora que la fase final se ejecutó; la afirmación posterior de “test cerrado” solo puede referirse a una fase particular, no a todo el proyecto. [E3, E4]

### Fugas, datos reales y comparabilidad

El registro perceptual original identificó cinco grupos de secuencias cruzadas y once movimientos de reparación. El revisor declarado fue `codex_visual_review`, no un experto humano. La auditoría reparada informa cero candidatos cruzados con dHash Hamming≤2; esto no detecta todas las vistas de una misma planta ni acredita separación por sesión. Además, un grupo histórico conectaba train y test: una nueva partición no borra la exposición previa a sus imágenes. [A, S; E4]

El conteo actual de originales produjo 1.062 imágenes train, **1.061 etiquetas** y 2.881 cajas, frente a 133/459 en val y 133/480 en test. `0117.jpg` carece de etiqueta. El híbrido usa pares completos; el baseline clásico v2 incluye esa imagen como fondo según `profiles.py` y su reporte. Para una campaña nueva, ausencia de label debe distinguirse de negativo humano verificado. No se modificó el original. [R, S; E6]

Todas las 3.820 cajas reales leídas tienen clase 0. No contienen madurez, medición del fruto ni identidad de planta/sesión en el formato YOLO. La inspección visual de `train/0275.jpg` muestra un capacho sostenido en mano sobre una mesa: el dominio real incluye ejemplos que no representan un cultivo denso. Es una observación puntual, no una estimación de prevalencia. Antes de calibrar escenas enteras a este conjunto se debe clasificar su dominio de adquisición usando solo desarrollo.

### Piloto visual v2 y diagnóstico del detector

Se verificaron ahora los 60 RGB, 60 labels y 60 previews contra los hashes del manifiesto: **180/180 coincidencias**. Hay 151 detecciones, partición 48/6/6 y 40 candidatos rechazados. Los estados latentes son 40 verdes, 19 transición, 69 pajizos y 23 secos; sus etiquetas entrenables siguen siendo monoclase. [R; E5]

Un detalle importante del manifiesto: **38 escenas contienen una planta y 22 contienen dos**. El piloto no equivale a la escena de revisión de veinte plantas. Las cámaras aceptadas son 38 `real_close` y 22 `real_mid`; ninguna `real_context`. No hay base para sostener robustez en escenas de cultivo amplias a partir de este piloto.

| Criterio histórico | Valor | Umbral registrado | Estado |
|---|---:|---:|---|
| Brecha máxima de bandas de área | 7,384 pp | ≤7 | Falla |
| Brecha media de composición | 1,899 pp | ≤3 | Cumple |
| Energía contextual de borde | 14,815 | ≥30 | Falla |
| Dispersión contextual de luminancia | 27,449 | ≥38 | Falla |
| Colisiones/abiertos/fruto oculto visible | 0 declarados | 0 | Cumple en auditoría guardada |

Los umbrales de borde y dispersión son heurísticas diagnósticas, no sustitutos validados de AP real. Conservar el rechazo histórico no obliga a optimizar esos proxies indefinidamente: una hipótesis nueva puede evaluar su utilidad mediante ablación predeclarada. Los fondos suavizados, las briznas subpíxel y las siluetas repetidas son mecanismos plausibles [H], no causas de transferencia demostradas.

La revisión visual nueva de `uchuva_s0000_c00_annotated.png` muestra un capacho muy cubierto por hojas: su registro tiene 1.855 píxeles visibles en una caja de 90×129, ocupación aproximada 0,160. El estado latente pajizo no garantiza que una persona pueda reconocerlo en ese RGB. La sombra, oclusión, enfoque y tamaño final requieren una política de abstención.

El diagnóstico guardado en val a confianza 0,25 muestra ΔTP con IoU≥0,75 de +30, +27 y −5 y ΔFN ausente de −30, −16 y +4. Es análisis exploratorio por umbral y emparejamiento IoU, distinto del cálculo de AP. La mejora por bandas pequeñas orienta experimentos de escala, carga y visibilidad; no permite afirmar causalidad ni significancia. [A; E5]

### Antecedente clásico sin reabrir su publicación

Se inspeccionó el resumen confirmatorio local: contiene 40 corridas y `test_consulted=false`; ninguna receta es `strong_candidate`. V2-E7 mejora mAP frente a E0R en 10/10 semillas, media +0,018161 e intervalo declarado [0,011340; 0,024982], pero pierde recall operacional y falla la tolerancia de borde. El informe distingue correctamente resultado científico negativo de dos ejecuciones contaminadas por lanzamiento duplicado, preservadas en cuarentena y reemplazadas. [A para resumen; D para reconstrucción completa de las cuarenta corridas; E6]

Este antecedente enseña que AP y utilidad operacional pueden divergir. No debe compararse su 0,54 de val directamente con el 0,68 híbrido: existen diferencias de partición, receta, aumentación online y presupuesto. Una referencia clásica en la nueva tarea requerirá entrenamiento con las mismas etiquetas multiclase, selección y exposición; reutilizar la receta es un comparador, no reabrir la campaña estudiantil.

## Hallazgos técnicos priorizados

| Prioridad | Hallazgo, evidencia y consecuencia | Acción |
|---|---|---|
| P0 | No hay GT real de maduración; `maturity` sintético es latente [R/S, E7] | Contrato separado y revisión/medición antes de clases definitivas |
| P0 | Test histórico consultado, además de fugas conocidas [A/R, E3–E4] | Nuevo holdout de captura; antiguo test pasa a evidencia exploratoria |
| P0 | `occlusion_proxy=1-visible_pixels/bbox_area` confunde forma con oclusión [S/R, E9] | Medir silueta aislada a igual cámara; distinguir ocupación y oclusión |
| P1 | `generate_annotation_dataset` sobrescribía config antes de comprobar compatibilidad al reanudar [S/R, E9] | Corregido: rechazo previo ante diferencias; falta sellar hashes de entradas y fuente |
| P1 | `DatasetConfig.validate` permite `reference_split=test/overall` [S, E7] | Bloquear esos valores en la próxima campaña; no usar CLI histórico como garantía de sellado |
| P1 | Las máscaras suelen descartarse (`keep_masks=false`); un blend representativo no reconstruye todas las escenas [A/S] | Guardar máscaras y especificaciones de escenas en los pilotos decisivos |
| P1 | Cajas desde extensión de máscara visible; min. 24 píxeles y lado 6 antes del resize [S] | Auditar correspondencia con reales y tamaños efectivos a 640 px; no inferir máscara amodal |
| P1 | `detection_diagnostics` empareja cajas sin considerar clase; exportador móvil exige `{0:calyx}` [S] | Evaluación conjunta localización/clase nueva; Android conserva su modelo monoclase |
| P1 | Fechas históricas importadas en un único commit del generador [S] | No inventar commits por ensayo; fuente/config/pesos con hashes para la próxima campaña |
| P2 | Grafo aceptaba autoridad externa y rutas no canónicas [S/R] | Validador reforzado y referencia externa sustituida por contrato del proyecto |
| P2 | README “madura”, workstream “siempre aislados”, migración inicial e instrucciones generales obsoletas [S] | Corregidos alcance, evidencia y autorizaciones en esta rama |

La auditoría de mallas sí alimenta `validate_cultivation_scene` en la ruta de dataset. El chequeo de malla se realiza antes de crear el ambiente y se amplía con un chequeo cáliz–suelo: no se debe convertir “cero colisiones” en garantía sobre todos los objetos de vegetación ambiental. `visible_hidden_fruit_count` inspecciona principalmente flags de ocultación; no mide madurez ni transparencia fisiológica. El fixture ejecutado no valida colisiones del cultivo entero.

El núcleo puro se puede probar sin `bpy`; las APIs Blender se importan de forma diferida. La primera ejecución de tests sin `PYTHONPATH` falló por importación, no por ciencia; con `PYTHONPATH=src` pasaron 131 pruebas en 90,457 s. No se instaló nada. Runtime de entrenamiento: Python 3.12.14, Torch 2.12.1+cu130, Ultralytics 8.4.114. Los resultados históricos registraban Python 3.12.13: no son entornos byte a byte idénticos. Blender es 5.1.2 con Python 3.13.9. GPU RTX 4050 Laptop, aproximadamente 6 GiB VRAM, RAM libre medida 8,42 GiB en un instante.

Un clon limpio carece de originales, pesos, venv y gran parte de `outputs/`; `assets/textures/current` y los recursos CC0 requieren inventario y hashes antes de una generación completa. No existe un workflow `.github` en el árbol remoto inspeccionado. No se justifica migrar SO, actualizar Blender ni agregar dependencias pesadas para resolver los hallazgos actuales.

## Instrucciones y grafo de contexto

La búsqueda del proyecto encontró un único `AGENTS.md`, sin overrides, `agent.md`, skills propios ni archivos bajo `.agents/` o `.codex/`. El `AGENTS.md` global existe pero está vacío; no se encontraron configuraciones explícitas de nombres alternativos o límite documental. El AGENTS raíz fue suministrado en esta sesión y además leído. El grafo y los planes son contexto leído por referencia, no una segunda autoridad automática. La documentación oficial describe la prioridad de overrides y el recorrido hasta el directorio de trabajo; un archivo presente no prueba por sí solo que se cargó. [S; S11]

Se retiró la sección de migración inicial ya cumplida y se registró la autorización específica para reformulación científica, multiclase y refactorizaciones. Se conservan límites de dependencias, datos, costes y lotes grandes. El protocolo de diez casos continúa siendo útil para promoción visual; no se ejecuta entero por cambiar un sidecar puro. Antes de promover cambios de geometría deberá existir revisión humana real, sin convertir un smoke en aprobación.

El grafo tenía 128 nodos y 236 aristas en el checkout inicial. Su validador comprobaba existencia de rutas/locators pero solo excluía tres prefijos de outputs; una contribución externa figuraba como evidencia autoritativa. Se reforzó la normalización y exclusión de fuentes externas/legado/drafts y se corrigió esa referencia de evidencia mediante el contrato propio. Se añadieron dos nodos y una arista para observaciones/tests. El resultado actual es 130 nodos y 237 aristas. Pasar el validador **no acredita veracidad de los resúmenes**, completitud experimental o aprobación humana.

## Estado del arte y decisión científica

La búsqueda priorizó fuentes originales hasta el corte, separando fecha de publicación de fecha de indexación. Los resultados de búsqueda pueden mostrar “publicado hace meses” para trabajos de 2021; se usaron las fechas del artículo. No se afirma prioridad mundial ni se promete aceptación editorial.

| Antecedente verificado | Qué resuelve y qué cambia en esta decisión |
|---|---|
| Boudon et al., L-Py, 2012, artículo [S1] | La generación estructural mediante L-systems está establecida. Mantener un árbol interpretable es infraestructura, no novedad autónoma |
| Duboudin et al., 2019, contribución de workshop [S2] | Blender, árboles frutales, anotación y randomización ya aparecen juntos. Descarta vender solo “generador Blender” |
| Fei et al., ICCV Workshops 2021 [S3] | Modelos 3D y GAN con restricción semántica para eficiencia de datos; CycleGAN visualmente plausible puede mover frutos. La preservación de etiquetas debe verificarse |
| Lei et al., Plant Phenomics 2024 [S4] | Helios genera imágenes anotadas y prueba transferencia; incluye interés de fondos sin fruto. Contexto y negativos son variables experimentales, no decoración |
| From blender to farm, PLOS ONE 2025 [S5] | Blender + SwinUNet + adaptación para fresa madura/inmadura ya existe; las limitaciones incluyen oclusión y daño. Maduración RGB con sintéticos tampoco basta como novedad |
| AGILE, CVPR Workshops 2025 [S6] | Difusión guiada por atención intenta preservar semántica entre dominios. Es alternativa competitiva, pero debe comprobar conservación de instancia y color si el color define la tarea |
| SynthSet, preprint inicialmente 2024 [S7] | Generación conjunta de imagen/máscara para segmentación agrícola. No se confirmó aquí una referencia editorial; no se presenta como artículo revisado por pares |
| Mounir et al., preprint julio 2026 [S8] | Invernadero procedural, SAM 3 e interpolación de pesos, con evaluación en datasets reales. Eleva el estándar de comparadores y hace poco novedosa la interpolación como eje del artículo |
| Sim-to-Real Fruit Detection…, preprint marzo 2026 [S9] | Reporta real-only mejor en dominio y utilidad híbrida bajo cambio de dominio. Es compatible con estudiar límites; no obliga a migrar a Isaac Sim |

La bibliografía local ya incluía FSPM, L-Py, botánica y Fei, pero este último solo como arXiv: su publicación ICCVW está verificada. Dos claves Kew duplican una fuente. La cobertura reciente de generación/adaptación era insuficiente frente a 2025–2026; se agrega metadata de fuentes nuevas sin PDFs. No se reinterpretan métricas Dice/IoU de segmentación como AP de detección ni resultados de fresa como evidencia en uchuva.

### Tres rutas sustantivas

| Ruta | Hipótesis y coste | Riesgo y decisión |
|---|---|---|
| **A. Control estructural, visibilidad y contexto con etiquetas observables** | A igual presupuesto real y pasos de entrenamiento, variación condicionada y verificable reduce errores de localización/clase bajo cambio de captura. Reutiliza Blender; necesita anotación experta y nuevo holdout | **Principal**. Aporta un mecanismo testeable y aprovecha los fallos encontrados. Se refuta si no mejora al control de igual cómputo o si sus ablaciones no explican la ventaja |
| B. Traducción semántica de renders mediante difusión/GAN | Reducir brecha de apariencia sin alterar posiciones, máscaras ni estado visual. Necesita reales de desarrollo y entrenamiento/QA adicional | Reserva. AGILE/Fei son cercanos; el color puede alterarse justo donde define clase. Solo probar si A pasa integridad y los errores apuntan a apariencia |
| C. Modelo fundacional como anotador asistido o detector adaptable | Menos minutos humanos por instancia manteniendo calidad. Necesita validar pseudoetiquetas y medir coste de corrección | Comparador posterior; no GT ni reemplazo automático del generador. SAM 3 reciente es pertinente, pero 6 GiB no autoriza suponer ajuste completo local viable |

La pregunta falsable de A es: **¿controlar por separado estructura/visibilidad y factores contextuales no diagnósticos permite aprender localización y estado observable de cada capacho con menos anotación real, manteniendo desempeño en nuevas sesiones de cultivo?** El efecto transferible es un protocolo y un mecanismo de generación/evaluación; no se afirmará generalización a otros cultivos sin ensayos adicionales.

Una intervención contrafactual mantiene identidad del órgano y modifica fondo/luz/cámara; otra modifica estado del órgano coherentemente. No se colocan frutos al azar para “romper correlaciones”. Las transiciones anatómicas se mantienen plausibles; para desmontar el atajo de altura se varían cámaras, cohortes y manejo, con auditoría de la distribución resultante. Una mejora debida solo a ver más veces datos reales debe desaparecer frente al control de exposición igualada.

El potencial editorial depende de evidencia fuerte en holdout externo, curvas de coste/etiquetas, ablaciones causales y liberación de contratos/configuraciones reproducibles. Un resultado negativo claro puede delimitar condiciones de fallo; no garantiza por sí solo publicación de alto impacto. Sin mediciones de fruto, el título y las conclusiones deben referirse a **estado visual del capacho**, no a madurez fisiológica de uchuva.

## Estrategia multiclase y validez

Diniz et al. observaron madurez a 75 DAA en una cohorte y 60 DAA en otra, y señalan que el cambio epidérmico del fruto puede preceder al del cáliz. Rodrigues et al. estudiaron otras condiciones y edades, con recomendación de cosecha después de 35 DAA. Los resultados no son umbrales universales intercambiables: usar las edades del generador como etiquetas reales sería inválido. [S10, S12]

Se propone probar **tres categorías de apariencia**, con nombres e IDs reservados únicamente para el protocolo candidato, antes de decidir si son reproducibles entre anotadores:

| ID propuesto | Nombre candidato | Regla visual inicial |
|---:|---|---|
| 0 | `calyx_green` | Tejido observable predominantemente verde, sin transición amarilla inequívoca |
| 1 | `calyx_transition` | Mezcla verde–amarilla visible en tejido suficiente; excluir balance de blancos dudoso |
| 2 | `calyx_straw` | Apariencia pajiza/amarilla observable; no asignar madurez del fruto por ese hecho |

Son una **propuesta de ingeniería apoyada en descripciones de transición**, no clases botánicas universales ni IDs activos. Se evita una cuarta clase “sobremaduro”: deterioro/sequedad/daño se registran por separado y pueden coexistir con distintas condiciones del fruto. Los sintéticos `dry_deteriorated` se revisan; no se convierten automáticamente en “sobremaduro” ni pajizo. Si transición es inestable entre expertos, fusionar categorías antes de confirmar el dataset y documentar la pérdida de granularidad.

Protocolo de anotación:

1. Conservar caja e identidad de cada instancia; fijar si la caja encierra solo lo visible o una extensión amodal. La opción inicial es extensión visible, por su correspondencia con máscaras, pero exige reauditar cajas reales o registrar ambas en una submuestra.
2. Dos anotadores independientes, cegados al estado sintético y a predicciones, etiquetan un piloto estratificado en color, tamaño, oclusión, iluminación y dominio. Cada uno registra clase visual, certeza, causa de ambigüedad y visibilidad del fruto. Adjudicación por un tercero o consenso documentado; conservar desacuerdos iniciales.
3. Casos ambiguos: `unknown`, `insufficient_visibility`, `color_uncertain`, `damaged` y `out_of_scope` como razones/atributos; no como falsas clases de madurez. Medir cobertura frente a exactitud de los casos retenidos. No borrar sus objetos y entrenarlos silenciosamente como fondo: usar cabeza de clasificación enmascarada o un formato con regiones ignoradas, o excluir la imagen completa del piloto multiclase si el entrenador no soporta ignore.
4. Medir acuerdo bruto, confusión, kappa ponderado o alfa ordinal, y desacuerdo de cajas mediante IoU. No fijar un kappa arbitrario como certificado de verdad; estimar intervalos y coste de adjudicación. Antes de la campaña, acordar con expertos el error máximo de clasificación de cosecha y los criterios de visibilidad.
5. Para madurez del **fruto**, capturar la unidad en planta con ID, fotografiar fruto tras apertura y medir color estandarizado, sólidos solubles, acidez y/o firmeza con protocolo agronómico. Registrar cohorte, fecha, manejo y cultivar/ecotipo. Separar valor medido, criterio de decisión agronómico y percepción RGB. No inventar umbrales locales de °Brix ni asignarlos por DAA sintético.

La primera intervención genera `uchuva.instance_observation/0.1`, un sidecar de **151 observaciones pendientes**: candidato visual sintético separado, clase de entrenamiento nula, madurez agronómica nula y ocupación de máscara diferenciada de oclusión. No constituye un dataset multiclase terminado.

Migración: conservar `calyx_single_class` y sus checkpoints; versionar un único esquema de observaciones, política de clases, hashes del diccionario y derivados. Consumidores afectados: `yolo_export.py`, `blender_annotations.py`, `blender_dataset.py`, `domain_analysis.py`, `hybrid_experiments.py`, `hybrid_study.py`, `hybrid_training.py`, `detection_diagnostics.py`, descriptores YAML y pruebas. Los previews tienen paleta/fuente monoclase. `export_mobile_detector.py` y `VisionEngine.kt` rechazan otro diccionario: Android seguirá con el manifiesto histórico hasta una adaptación independiente. Gazebo conserva IDs, unidades, jerarquía y procedencia; no necesita SDF ni métricas 3D para esta pregunta.

## Verificación nueva y límites de cierre

Además de las pruebas del baseline, se ejecutaron seis pruebas del contrato de observación, cuatro del grafo, dos de reanudación y doce helpers de dataset. Las pruebas de reanudación ejercitan el entrypoint real con fixtures y comprueban que un cambio de fenología falla sin escribir config, YAML ni manifiesto. Se conserva el log del fallo inicial de importación; invocar módulos como `tests.test_*` tampoco funcionó en este entorno, por lo que los comandos finales usan discovery.

La suite completa de cierre pasó con **140 tests en 112,319 s**, registrada en `final_tests.log`. La preservación de cambios preexistentes se comprobó por SHA-256: once archivos ajenos idénticos; al retirar en memoria nuestras inserciones/corrección del grafo, su contenido vuelve a coincidir con el hash inicial. No se revirtió ningún cambio del usuario para hacer esa comprobación.

El fixture Blender usó dos máscaras EEVEE de 128×128 y tardó 18,437 s dentro del proceso: silueta aislada 3.196 píxeles, semitapada 1.598. Ambas tenían `mask_fill_ratio=0,780273`; la oclusión correcta era 0 y 0,5. El campo histórico `occlusion_proxy` permanece para compatibilidad; la nueva medición separada no lo presenta como tasa física. Esto prueba la distinción matemática y el pipeline de una escena controlada, no el estado de toda la vegetación.

No se ejecutó entrenamiento nuevo, lote de cultivo ni campaña confirmatoria. No se atribuye aprobación a una validación humana pendiente. La siguiente intervención está especificada en el [plan de continuidad](../plan_auditoria_cientifica_blender_2026-09-08.md), con artefactos, comandos, criterios y registro vivo.

## Evidencia del repositorio

Las rutas de código se refieren al commit auditado salvo archivos nuevos, identificados como intervención. Los artefactos locales contienen datos privados y no se publican automáticamente.

| ID | Referencia precisa |
|---|---|
| E1 | [Commit auditado](https://github.com/dryanguasr/SyntheticPlantGeneration/commit/8fa6ddc8293d403134873a433d6c6fc5a7321dd4); árbol GitHub `52928957fd695a2b7ee927890610002413557b98` |
| E2 | [Reporte híbrido](https://github.com/dryanguasr/SyntheticPlantGeneration/blob/8fa6ddc8293d403134873a433d6c6fc5a7321dd4/docs/reports/resultado_dataset_hibrido_2026-08-01.md); `outputs/experiments/checkpoint_interpolation_scale80_seed_1000_v1/checkpoint_interpolation_result.json` |
| E3 | `outputs/experiments/hybrid_fidelity_v2_leakage_repaired_20260811/{phase_a_decision.json,phase_a_summary.csv,selection.lock.json,final_test/final_test_summary.json}`; SHA del último `c4257078a272b0f3b05d4f8ebdaf3ff033884542b0fb04e8bfdba3ead54db9d0` |
| E4 | [Revisión de fugas](https://github.com/dryanguasr/SyntheticPlantGeneration/blob/8fa6ddc8293d403134873a433d6c6fc5a7321dd4/docs/governance/real_split_perceptual_review_20260811.json); `repaired_source_audit.json` del estudio y `outputs/logs/hybrid_fidelity_v2_final_test.out.log` |
| E5 | [Reporte del piloto](https://github.com/dryanguasr/SyntheticPlantGeneration/blob/8fa6ddc8293d403134873a433d6c6fc5a7321dd4/docs/reports/mejoras_virtuales_prioritarias_2026-08-14.md); `outputs/audits/virtual_fidelity_v2_pilot_seed_16000/pilot_audit.json`; dataset homónimo; `outputs/diagnostics/detector_real_val_multiseed_v2/detection_diagnostic_summary.csv` |
| E6 | [Confirmación clásica](https://github.com/dryanguasr/SyntheticPlantGeneration/blob/8fa6ddc8293d403134873a433d6c6fc5a7321dd4/docs/reports/aumento_clasico_v2_confirmatory_2026-08-28.md); `outputs/classical_augmentation_v2/metrics/confirmatory/confirmatory_summary.json`; `src/uchuva_classical_augmentation/v2/profiles.py` |
| E7 | [Fenología](https://github.com/dryanguasr/SyntheticPlantGeneration/blob/8fa6ddc8293d403134873a433d6c6fc5a7321dd4/src/uchuva_lsystem/phenology.py), funciones `reproductive_phenology`, `coherent_stage_sequence`; [dataset](https://github.com/dryanguasr/SyntheticPlantGeneration/blob/8fa6ddc8293d403134873a433d6c6fc5a7321dd4/src/uchuva_lsystem/blender_dataset.py), `DatasetConfig.validate`, `_build_dataset_scene`, `_render_dataset_capture` |
| E8 | `outputs/human_validation/photoreal_protocol_v1/human_review.csv`; `docs/guides/protocolo_validacion_humana.md` |
| E9 | [Anotaciones](https://github.com/dryanguasr/SyntheticPlantGeneration/blob/8fa6ddc8293d403134873a433d6c6fc5a7321dd4/src/uchuva_lsystem/blender_annotations.py), `_snap_and_save_image`; intervención `annotation_contract.py`, `blender_annotation_contract_smoke.py`, `_validate_resume_configuration` |
| E10 | `outputs/audits/scientific_route_20260908/`: `evidence.json`, logs, `instance_observations.jsonl`, `blender_smoke/report.json`, `preexisting_changes.json`; reproducible con `scripts/audit_scientific_evidence.py` |

## Fuentes externas

- **S1.** Boudon et al. (2012), [L-Py: An L-System Simulation Framework…](https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2012.00076/full), Frontiers in Plant Science; DOI 10.3389/fpls.2012.00076. Texto primario consultado.
- **S2.** Duboudin, Petit y Chen (2019), [Toward a Procedural Fruit Tree Rendering Framework for Image Analysis](https://arxiv.org/abs/1907.04759). Registro primario con referencia a workshop de ciencias de plantas; no tratado como gran ensayo confirmatorio.
- **S3.** Fei et al. (2021), [Enlisting 3D Crop Models and GANs…](https://openaccess.thecvf.com/content/ICCV2021W/CVPPA/html/Fei_Enlisting_3D_Crop_Models_and_GANs_for_More_Data_Efficient_ICCVW_2021_paper.html), ICCV Workshops, pp. 1269–1277. Página/indexación CVF y abstract primario verificados.
- **S4.** Lei et al. (2024), [Simulation of Automatically Annotated Visible and Multi-/Hyperspectral Images…](https://doi.org/10.34133/plantphenomics.0189), Plant Phenomics 6:0189. Metadatos y extractos primarios indexados contrastados con [laboratorio de los autores](https://baileylab.ucdavis.edu/publications/index.html); acceso directo al texto completo limitado por redirección/captcha. No se reproducen cifras de rendimiento no verificadas.
- **S5.** [From blender to farm: Transforming controlled environment agriculture with synthetic data and SwinUNet for precision crop monitoring](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0322189) (24 abril 2025), PLOS ONE; DOI 10.1371/journal.pone.0322189. Texto completo consultado.
- **S6.** Ranario et al. (2025), [AGILE: A Diffusion-Based Attention-Guided Image and Label Translation…](https://arxiv.org/html/2503.22019v1). Texto de autores consultado; referencia CVPR Workshops verificada con CVF y laboratorio. El PDF CVF devolvió 403; no impidió leer el texto de autores.
- **S7.** Heschl et al., [SynthSet: Generative Diffusion Model for Semantic Segmentation in Precision Agriculture](https://arxiv.org/abs/2411.03505), envío inicial 5 noviembre 2024. Preprint consultado; sin referencia editorial confirmada en esta auditoría.
- **S8.** Mounir et al. (20 julio 2026), [Text-conditioned Segmentation for Tomato Phenotyping via Procedural Synthetic Data](https://arxiv.org/html/2607.18576v1). Preprint, no aceptación ECCV presumida por el nombre de un repositorio/dataset. Texto completo consultado.
- **S9.** [Sim-to-Real Fruit Detection Using Synthetic Data: Quantitative Evaluation and Embedded Deployment with Isaac Sim](https://arxiv.org/abs/2603.28670) (30 marzo 2026). Preprint; abstract consultado, no réplica ni verificación independiente de sus métricas.
- **S10.** Diniz, Cardillo y Novembre (30 agosto 2025), [Development and maturation of cape gooseberry fruits](https://comunicatascientiae.com.br/comunicata/article/download/4281/1359), Comunicata Scientiae 16:e4281; DOI 10.14295/CS.v16.4281. PDF primario de diez páginas consultado, especialmente resultados de cohortes y relación cáliz/fruto.
- **S11.** OpenAI, [Custom instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md), documentación oficial consultada al corte.
- **S12.** Rodrigues et al. (19 marzo 2021), [Characterization of physiological maturity of Physalis peruviana L. fruits](https://ojs.uel.br/revistas/uel/index.php/semagrarias/article/view/40197), Semina: Ciências Agrárias 42(3):929–948; DOI 10.5433/1679-0359.2021v42n3p929. Abstract y metadatos primarios consultados.
