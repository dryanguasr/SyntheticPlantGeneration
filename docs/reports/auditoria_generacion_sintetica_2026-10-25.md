# Auditoría independiente del generador de uchuvas y su puente a Gazebo

**Corte:** 25 de octubre de 2026  
**Repositorio:** `dryanguasr/SyntheticPlantGeneration`  
**Commit examinado:** `74b43d205927fd66d5ecd9833f7de7eed27972b5` (`main`, 14 de octubre de 2026)  
**Naturaleza:** revisión de código y ejecución de pruebas Python; **no** certificación de renders, física ni botánica de campo.

## 1. Dictamen ejecutivo

La arquitectura morfológica es una buena base para transferir el desarrollo a los estudiantes: el árbol de órganos serializable tiene una fuente de verdad independiente de Blender, las semillas permiten reproducir una configuración completa y ya existe un puente de exportación a Gazebo. Durante la auditoría **no se encontraron excepciones que impidieran generar las 700 plantas examinadas**.

Se confirmaron **tres defectos de contrato** que conviene resolver antes de calibrar con mediciones reales: el radio de orden 3 hereda el rango de orden 1; el máximo de frutos queda incumplido después de reasignar las cohortes; y el validador utiliza umbrales fijos ajenos a los parámetros efectivos. Además, la procedencia de parámetros presenta inconsistencias y el actual exportador de Gazebo todavía no representa una cosecha física completa.

**Decisión recomendada:** congelar la línea basal y corregir esos contratos; iniciar medición de campo y revisión de video con identificadores trazables; evaluar cosecha rígida con el robot virtual; abordar `Springy` únicamente como hipótesis secundaria, mediante un piloto de ramas seleccionadas y medidas de fuerza-desplazamiento.

El código **no se corrigió en esta auditoría**. Las incidencias que siguen son observaciones y propuestas de trabajo, no pruebas de que un parche ya exista.

## 2. Alcance, muestra y nivel de evidencia

Se examinó el código de `src/uchuva_lsystem/`, las rutas relevantes de `src/uchuva_gazebo/`, los scripts de exportación y la documentación experimental. La ejecución independiente utilizó Python 3.12.14.

| Inspección o prueba | Resultado | Alcance de la afirmación |
|---|---:|---|
| Cuatro presets, `legacy_independent`, semillas 0–99 por preset | 400 plantas | Árbol morfológico puro |
| Ruta de dataset `one_to_five` / `under_one_percent`, `literature_cohort_v1`, semillas 0–299 | 300 plantas | Antes de crecimiento síncrono y render |
| Excepciones al generar las 700 plantas | **0** | No equivale a ausencia de advertencias |
| Semillas repetidas 0, 1, 23, 77, 299, misma configuración | **5/5 idénticas** | Determinismo, no independencia entre subflujos |
| Pruebas morfología/fenología/crecimiento seleccionadas | **15/15 pasaron** | Subconjunto del núcleo Python |
| Pruebas puras de Gazebo seleccionadas | **18 pasaron**; un módulo sin importar | `cv2` ausente para prueba multivista |
| Descubrimiento general de tests | 206 pruebas; 21 errores, 185 restantes sin fallo | Errores de importación/ejecución asociados a `cv2` (20) y `torch` (1), no fallos de aserción demostrados |

**Límites importantes:** no se ejecutaron Blender ni Gazebo, no se inspeccionaron nuevas mallas renderizadas, colisiones reales, dinámica de ramas, robot cosechador ni una campaña de campo. El dataset real original y algunos `outputs/` no forman parte del clon limpio. Los resultados de entrenamientos citados más adelante se **recuperaron de informes históricos**; no se reentrenó ningún detector.

Para reproducir el síntoma más claro del tope de frutos en el commit auditado:

```bash
PYTHONPATH=src python3 - <<'PY'
from uchuva_lsystem.blender_dataset import _morphology_params_for_target
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.validation import validate_morphology_tree

params = _morphology_params_for_target({
    "object_count_band": "one_to_five",
    "box_area_band": "under_one_percent",
})
print("Máximo declarado:", params["reproduction"]["target_reproductive_units_range"]["max"])
for seed in range(5):
    plant = generate_morphology_tree(
        seed, params=params, phenology_model="literature_cohort_v1"
    )
    report = validate_morphology_tree(plant)
    print(seed, report["summary"]["fruiting_reproductive_unit_count"])
PY
```

Resultado del muestreo original, semillas 0–4: **10, 5, 6, 10 y 8** frente a máximo nominal 4. Si se ejecuta después de los correctivos, esos resultados deben cambiar. Las pruebas anteriores tampoco incluyen aún un test específico de regresión para este contrato.

## 3. Defectos confirmados de morfología y validación

### M1 — Radio por orden de ramificación (prioridad P0)

**Ruta:** `src/uchuva_lsystem/parameters.py`, `grammar.py`, `validation.py`.

La tabla de radios especifica órdenes 0, 1 y 2, pero `trained_trellis` admite orden 3. El fallback de `grammar.py` asigna al orden 3 el rango de orden 1, contraviniendo el supuesto explícito de decrecimiento de radio con el orden. Sobre las 300 plantas de dataset:

| Orden | Radio medio (cm) |
|---:|---:|
| 0 | 0,220019 |
| 1 | 0,108013 |
| 2 | 0,045645 |
| **3** | **0,108029** |

Los entrenudos de orden 3 son **6.316/33.883 (18,64 %)**; el aviso de radio aparece en **295/300 plantas**. Estas tasas dependen del muestreo y del preset: difieren del porcentaje estimado por la revisión previa.

**Corrección:** definir rango explícito para orden 3 o una regla decreciente documentada; exigir parámetros para cada orden habilitado; probar radio local padre/hijo y uniones, no solo medias de una muestra.

### M2 — Presupuesto reproductivo incumplido tras cohortes (P0)

**Ruta:** `src/uchuva_lsystem/grammar.py`, especialmente `_enforce_reproductive_unit_target` y `_apply_literature_cohorts`.

La normalización contabiliza unidades con fruto y cáliz, pero la reasignación posterior de cohortes puede convertir flores en frutos. La metadata conserva el límite previo mientras cambia el conteo real. Con máximo 4, **267/300 plantas (89 %) superan el tope**, con rango final observado de **4–15 frutos**.

**Corrección:** acordar si el presupuesto se refiere a unidades reproductivas totales, unidades con fruto, órganos visibles o anotaciones aceptadas. Aplicar/verificar el límite en la etapa final pertinente, actualizar metadatos y conservar explícita la distribución floral. Un arreglo que elimine indiscriminadamente flores puede crear otro sesgo.

### M3 — Validador desacoplado del preset efectivo (P0)

**Ruta:** `src/uchuva_lsystem/validation.py`, `parameters.py`.

`validation.py` carga el preset inicial y utiliza umbrales fijos `|curl| > 0,08` o `|twist| > 4°`, aunque el generador admite aproximadamente curl entre `-0,10` y `0,16`, y torsión entre `-8°` y `8°`. Resultado: **23.331/33.883 hojas (68,86 %)** quedan señaladas por esta regla. Las **700 plantas** del muestreo tienen al menos una advertencia; esto **no** demuestra imposibilidad matemática de obtener una planta sin advertencias bajo toda configuración.

Parte de las advertencias sobre luz se producen antes de que el crecimiento de escena calcule los proxies correspondientes. Se requiere un validador **por etapa**, alimentado con un snapshot o hash de **parámetros efectivos** (incluyendo overrides de dataset), que separe integridad, contrato, plausibilidad botánica y geometría final. No se deben suprimir alarmas elevando arbitrariamente los umbrales.

## 4. Hallazgos adicionales relevantes

| ID / prioridad | Evidencia y efecto | Acción propuesta |
|---|---|---|
| **M4 / P0**: procedencia | En `trained_trellis`, 91 entradas: 55 supuestos manuales, 17 heurísticas, 6 inferencias de dataset, 6 por medir, 4 restricciones y 3 etiquetadas como literatura; **0 medidas reales etiquetadas**. Dos de las tres etiquetas de literatura proceden de heurísticas acotadas, sin `source_ids` comprobados. La cohorte agrega `first_bifurcation_node` sin `status`: **300/300 auditorías activas de procedencia inválidas**. | Hacer canónica toda entrada incorporada/reescrita, con método, fuente y evidencia; distinguir una etiqueta declarada de una referencia verificada. |
| **M5 / P1**: subflujos aleatorios | La semilla y parámetros iguales reproducen el árbol, pero variar solo el perfil fenológico cambia estructura: semilla 0, perfiles `mixed_early`/`mixed_balanced`/`mixed_late`, **127/111/157 nodos**. El RNG de fenología separado no aísla todo consumo aleatorio de la gramática. | Congelar morfología para ablaciones de apariencia o desacoplar subflujos según contrato científico; no exigir identidad si el perfil pretende representar edades estructurales diferentes. |
| **M6 / P1**: fruto frente a cáliz | **187/300 plantas** presentan advertencia dimensional. En **48/300**, el diámetro nominal del fruto supera el ancho nominal `2*radio_cáliz*inflación`; razón máxima **1,0732**. | Medir envolventes y revisar correlaciones de escala por cohorte; **no** presentarlo como una colisión de malla ya demostrada. |
| **M7 / P1**: proxy de ancho | **259/300 plantas** activan ancho excesivo; el cálculo suma longitudes laterales proyectadas, sin representar adecuadamente azimut o solape. | Comparar con AABB/huella reales tras adaptación y render; el 86,33 % es una **tasa de alertas proxy**, no una tasa de plantas 3D inválidas. |
| **M8 / P1**: ficha de campo y esquema | `scripts/generate_expert_questionnaire_pdf.py` ofrece `measured_local`, mientras `provenance.py` no lo admite como estado canónico y lo transforma en `to_be_measured`. Los overrides de pecíolo pasan de **2,0–5,2** a **3,5–5,8 cm** conservando etiqueta de fuente anterior. | Usar provisionalmente `real_dataset_measured` con método/fuente verificables, o migrar esquema de manera explícita; actualizar procedencia al sobrescribir valores. |

### Escala: corrección de una sospecha anterior

En esta ruta hay conversión explícita: **0,08 unidades Blender/cm** y **8 unidades Blender/m** en el exportador Gazebo. Por tanto, `10 cm → 0,8 BU → 0,10 m` es internamente coherente. La longitud acumulada del eje principal de la ruta dataset fue **22,285–28,427 cm** (media **25,394 cm**) antes de adaptaciones; **no** es necesariamente la altura final vertical del arbusto. Los valores de poste `3,05–3,55` de esa escena están en unidades de escena, no en metros demostrados. El preset de campo Gazebo usa otra escala/población. Sigue faltando **calibración física contra cultivo medido**, pero la comparación directa «25 cm frente a postes de 3 m» no prueba por sí sola un bug de conversión.

## 5. Gazebo: representación presente y brecha de interacción

La arquitectura `src/uchuva_gazebo/interfaces.py` ya prevé niveles LOD y describe una unión de pedicelo desprendible; ese contrato es **semántico**, no una articulación física operativa. `scripts/export_gazebo_field.py` crea vegetación y tutorado, con colisiones principalmente para ejes principales, estructuras y postes; las ramas laterales, hojas y capachos de esa ruta siguen esencialmente **visuales**. Incluso con `--individual-calyces`, los órganos separados continúan estáticos y sin masa/inercia, `collision` ni `joint` físico. Un brazo podría atravesar visualmente una copa sin que el motor reporte contacto.

El OBJ exportado actualmente contiene vértices en coordenadas globales y los capachos individuales quedan con pose de origen; **no basta con pasar de `static=true` a `false`**. Una versión dinámica requiere geometría en marco local, poses consistentes (`T_world_link * p_link = p_world`), masas/inercia físicamente plausibles y colisionadores simples específicos por órgano.

**Inconsistencia concreta de proxies:** `blender_geometry.py` elimina sag para ciertas fases de tutorado, mientras `collisions.py` lo sigue aplicando. Un testigo Python que compara las fórmulas sin ejecutar Blender halló discrepancias máximas en Z de aproximadamente **2,328 / 2,397 / 2,508 mm** para ramas de orden 1 en semillas 0/1/73. Es una inconsistencia entre interpretaciones del código; **no** se observaron directamente penetraciones dentro de Gazebo.

Los informes anteriores (`docs/reports/cierre_localizacion_3d_2026-10-05.md`) documentan **37/388 localizaciones correctas (9,54 % recall, precisión conjunta 80,43 %)** para el piloto 3D reservado. Es evidencia histórica recuperada, no un resultado nuevo de esta auditoría ni demostración de cosecha. La triangulación multivista existente supone objetivo estático entre vistas; una rama flexible en movimiento requiere estimar antes del contacto, readquirir o usar seguimiento dinámico con tiempo.

### Secuencia propuesta para la integración del robot

1. **R0, base geométrica:** una planta, un objetivo, escala e identidades conocidas, colisiones y separación inicial verificadas.
2. **R1, cosecha con pose ideal (`oracle`):** prueba de alcance, planificación, retención y corte sin confundirlos con detección.
3. **R2, percepción real del robot virtual:** RGB/RGB-D y localizador propios; usar ground truth solo para evaluar.
4. **R3, dificultad controlada:** varios objetivos, distintas alturas, oclusión, acceso lateral y obstáculos.
5. **R4, evaluación congelada:** escenas/semillas no usadas para ajuste; registrar éxitos, fallos y tiempos para **todos** los objetivos definidos de antemano.

Una cosecha completa exige objeto identificado, pose válida del efector, retención, evento de corte/desprendimiento, retirada sin caída y depósito. La desaparición de una malla o una animación terminada **no** basta para afirmar cosecha física. Reportar éxito *end-to-end* y condicionado por intento, error al pedicelo, contactos prohibidos, caídas y tiempo por etapa.

## 6. Hipótesis secundaria: `Springy`

El modelado flexible es **técnicamente factible como aproximación discreta**, pero todavía no hay mediciones de rigidez/amortiguamiento que avalen sus parámetros ni un banco rígido estable que sirva de control. Proponer un MVP con **1–3 ramas** relevantes, **2–4 segmentos** por rama, un grado de flexión inicial y luego ampliar solo si datos e interacción lo justifican.

Modelo torsional orientativo: `τ = -kθ(q - q0) - cθ·q̇`, con `kθ` en N·m/rad y `cθ` en N·m·s/rad. Medir desplazamiento ante fuerza conocida y recuperación libre; no atribuir rigidez absoluta a un video de una rama movida por viento desconocido. Evitar duplicar la deformación estática heurística que ya calcula `cultivation.py`. La nomenclatura SDFormat correcta incluye `spring_reference`, **`spring_stiffness`** y `damping`, pero hay que verificar el motor físico concreto.

Comparar rígido/flexible con **misma geometría, objetivos, robot, sensores y controlador**. Medir error de desplazamiento respecto a una referencia independiente, contactos/éxito, estabilidad de integración al reducir `dt`, coste computacional y realismo visual. La flexión puede dificultar la cosecha; ello sería un resultado científico válido. Su movimiento **no corrige automáticamente** colisionadores ausentes ni una geometría inválida.

Puerta de decisión: continuar solo si la complejidad adicional ofrece una mejora medible de fidelidad o modifica una conclusión de ingeniería respaldada por ensayos. De lo contrario, registrar la factibilidad y posponer el modelo.

## 7. Prioridades de transferencia y criterios de aceptación

| Etapa | Entregable verificable | Criterio mínimo |
|---|---|---|
| **P0. Integridad** | Tabla de radios completa; presupuesto postcohorte; validador por etapa/override; procedencia consistente | Pruebas nuevas que fallan antes y pasan después; metadatos coherentes; base congelada |
| **P1. Campo y video** | Manifiesto por finca/visita/planta/órgano, medición física, incertidumbre y procedencia | No medir profundidad métrica desde video monocular sin referencia; separar observado de inferido |
| **P1. Calibración** | Preset local versionado y evaluación de distribución física y proyectada | Divisiones por planta/sesión (sin fuga de fotogramas); comparar con baseline sin retocar el test reservado |
| **P1. Robot rígido** | Escena de una planta, contrato de frames/colisiones, episodios `oracle` y perceptivos | Desglose detección→localización→alcance→corte→depósito con denominadores completos |
| **P2. Springy** | Piloto pareado de ramas de interés y mediciones mecánicas | Fidelidad/coste medidos o decisión explícita de no seguir |

La caracterización debe registrar unidad, instrumento, fecha, punto anatómico, planta, estrato, observador y una nota de incertidumbre. Parámetros observables (longitudes, diámetros, conteos, tutorado) pueden calibrarse con medidas directas; parámetros latentes (probabilidades de brotación, vigor, rigidez) requieren identificabilidad, sensibilidad y modelos derivados. No asignar a las etiquetas sintéticas la categoría de verdad de campo. La apariencia del capacho no demuestra por sí sola madurez fisiológica del fruto.

Se recomienda una prueba piloto del protocolo de medición con unas pocas plantas antes de ampliar la campaña; cualquier tamaño de muestra inicial será **exploratorio** hasta justificar representatividad y precisión. La fecha de cierre institucional del macroproyecto según el acta compartida es **30 de noviembre de 2026**, por lo que la cosecha rígida mínima y la trazabilidad tienen preferencia sobre un motor flexible extenso.

## 8. Relevancia experimental y cuestiones abiertas

La auditoría científica histórica (`docs/reports/auditoria_cientifica_blender_2026-09-08.md`) había señalado que el dato sintético no mejoró consistentemente el detector. La evaluación híbrida multisemilla recuperada reporta una diferencia media aproximada **+0,0015 mAP50–95**, con **2 de 3 semillas negativas**. Los defectos M1–M3 *podrían* contribuir a la brecha, pero **no se ha demostrado causalidad**. Tampoco se pueden promocionar como «test externo intacto» datos reales ya consultados repetidamente en desarrollo.

Quedan pendientes como mínimo: mediciones botánicas locales, mallas y colisiones comparadas en Blender/Gazebo, masa y dinámica del órgano, interfaz concreta del robot estudiantil, protocolo de corte/retención, validación de madurez y ensayo físico de rama. Ninguno se da por aprobado por el hecho de que la morfología Python sea determinista.

## 9. Índice de evidencia y referencias internas

La ruta `/tmp` usada por una auditoría previa y los archivos de análisis fuera del repositorio **no son artefactos portables**. Este informe incorpora los resultados consolidados y un comando mínimo para el caso de frutos; para reproducir todas las estadísticas y hashes deben versionarse en una entrega técnica posterior los harnesses y manifiestos, manteniendo sus parámetros y semillas fijados.

**Código principalmente revisado:**

- `src/uchuva_lsystem/parameters.py`, `grammar.py`, `validation.py`, `provenance.py`, `blender_dataset.py`;
- `src/uchuva_lsystem/blender_geometry.py`, `growth.py`, `cultivation.py`, `collisions.py`, `sparse_pilot.py`;
- `src/uchuva_gazebo/interfaces.py`, `field.py`, `multiview.py`, `scripts/export_gazebo_field.py`;
- `scripts/generate_expert_questionnaire_pdf.py` y `tests/`.

**Documentación contrastada:** `docs/reports/auditoria_cientifica_blender_2026-09-08.md`, `docs/reports/cierre_localizacion_3d_2026-10-05.md`, `docs/reports/informe_virtual_karen_caroline_2026-10-14.md` y `AGENTS.md`. Los documentos del macroproyecto suministrados por el profesor sirvieron para acotar el alcance institucional, pero no son mediciones del cultivo ni un inventario certificado del robot.

**Fuentes técnicas primarias para futuras implementaciones:** [REP 103, unidades y frames](https://reps.openrobotics.org/rep-0103/), [SDFormat 1.10, joints](https://sdformat.org/spec/1.10/joint/), [Gazebo Sim 8, Detachable Joints](https://gazebosim.org/api/sim/8/detachablejoints.html), [OpenCV, calibración de cámara](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html), [scikit-learn, validación por grupos](https://scikit-learn.org/stable/modules/cross_validation.html).

**Estado de cierre de esta auditoría:** diagnóstico documentado; **sin parches del generador ni validación nueva en campo/Blender/Gazebo**. Las correcciones y pruebas de regresión deben realizarse en commits posteriores con evidencia específica.
