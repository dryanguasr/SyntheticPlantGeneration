# Plan de continuidad científica de Blender y maduración por instancia

## Objetivo y estado de partida

Construir y contrastar una generación de escenas de cultivo de uchuva que reduzca errores de localización 2D y clasificación por estado observable de cada instancia mediante control de estructura, visibilidad y contexto. La madurez agronómica del fruto solo se incorporará con verdad de terreno pareada y protocolo humano. El cierre científico requiere evaluación real independiente; una implementación funcional no confirma la hipótesis.

Este documento es el **plan autocontenido y registro vivo**. No depende de una goal activa en la interfaz ni de comandos especiales de Codex. El informe complementario es [la auditoría del 8 de septiembre](reports/auditoria_cientifica_blender_2026-09-08.md), con matriz histórica, fuentes y hallazgos. El plan de reestructuración anterior documenta otra intervención ya terminada; no se reabre.

Corte auditado mediante conector GitHub y checkout: `dryanguasr/SyntheticPlantGeneration`, `main`, commit `8fa6ddc8293d403134873a433d6c6fc5a7321dd4`, 2026-09-03 15:32:31 UTC. Rama de trabajo: `codex/auditoria-cientifica-blender-20260908`. Directorio local: `C:\dev\SyntheticPlantGeneration`. Al empezar había cambios de Android y del grafo: preservar todos. Los archivos de esta intervención están en el árbol de trabajo; revisar `git diff` y archivos nuevos antes de cualquier commit. No incluir cambios ajenos por accidente.

Decisiones ya tomadas y autorizadas: reformular dentro del frente Blender, migrar a multiclase y refactorizar con justificación experimental. No pedir otra aprobación general. La publicación clásica permanece con estudiantes. Gazebo solo conserva identidad, jerarquía, unidades y procedencia; quedan excluidos SDF, física robótica completa y localización 3D. No contratar recursos, subir datos privados, instalar dependencias sin justificación/autorización ni lanzar campañas largas sin presupuesto. No cambiar los originales ni retirar código local sin verificar que Git realmente lo conserva.

Hechos iniciales que condicionan el trabajo:

- El test histórico fue consultado durante desarrollo. El estudio híbrido posterior da +0,001533 mAP50–95 medio en tres semillas, dos negativas; no prueba superioridad general.
- El piloto v2 está rechazado para escalado: 60 imágenes, 151 instancias, 40 rechazos, escenas de una o dos plantas. Conservarlo como control, no lanzar otra tanda igual sin una pregunta discriminante.
- Las etiquetas reales actuales son monoclase: 2.881 cajas train, 459 val y 480 test. Hay 1.062 imágenes train pero 1.061 labels; `0117` sin label no es automáticamente negativo verificado.
- Existe GPU RTX 4050 Laptop de unos 6 GiB, Blender 5.1.2, Python de entrenamiento 3.12.14 y Ultralytics 8.4.114/Torch 2.12.1+cu130. Blender usa Python 3.13.9. Redescubrir disponibilidad en otra máquina.
- No hay baseline humano promovido en `outputs/human_validation`; la revisión pendiente no puede darse por aprobada.

## Hipótesis y política de etiquetas

Hipótesis principal: con el mismo presupuesto de etiquetas reales, misma inicialización y número de actualizaciones, entrenar con escenas sintéticas que controlen visibilidad/estructura y eviten correlaciones espurias de contexto mejora el AP conjunto de localización y clase en sesiones reales independientes frente a real-only y randomización sintética genérica.

El esquema inicial implementado es `uchuva.instance_observation/0.1`. Contiene identidad, caja, convención de caja, candidato de apariencia sintético, observación visual pendiente, madurez agronómica desconocida, estado de revisión y métricas de visibilidad. `training_class_id=null` impide confundir preparación con una migración terminada. No se ha cambiado el exportador YOLO ni los pesos móviles.

Propuesta para estudio de acuerdo: tres clases visuales, `calyx_green`, `calyx_transition`, `calyx_straw`, IDs candidatos 0/1/2 en un **diccionario nuevo**; el 0 del baseline significa `calyx` y jamás se interpretará con el diccionario nuevo. Sequedad/daño son atributos, no una clase de fruto “sobremaduro”. Conservar `unknown` y razones de abstención fuera de las clases de madurez. Antes de entrenamiento se debe congelar el diccionario, nombres, versión, reglas, procedencia de cada anotación y hash de la política.

Se necesitan dos anotadores cegados a metadata sintética y predicciones. El piloto debe contener tamaños, oclusiones, iluminación y condiciones visuales diversas; medir confusión, acuerdo e intervalos, tiempo por etiqueta y adjudicación. Para madurez real: capturar mismo ID de unidad antes y después de abrir el cáliz y registrar medidas agronómicas; expertos fijan los criterios locales. Si no es posible medir o predecir el fruto oculto, mantener explícitamente la tarea de apariencia y reportar el límite de observabilidad.

## Hitos por dependencia

| Hito | Trabajo y módulos | Aceptación y artefactos |
|---|---|---|
| M0 — evidencia y base ejecutable | Auditoría, `audit_scientific_evidence.py`, `annotation_contract.py`, CLI de revisión, fixture Blender, protección de resume y grafo | **Completado en esta intervención**, sujeto a revisión del diff; evidencia y logs bajo `outputs/audits/scientific_route_20260908/` |
| M1 — procedencia y seguridad experimental | Sellar entradas del generador/entrenador, rutas resueltas y hashes de config, versión, assets, perfiles, diccionario y revisión. Bloquear `test/overall` como referencias de una campaña nueva. Reutilizar helpers de `hybrid_study.py`; no crear un segundo entrenador | Fixture prueba que cambios de fuente/perfil o diccionario impiden resume antes de escribir. Reanudar sin cambios produce el mismo manifiesto. No requiere render |
| M2 — observabilidad y dataset real de desarrollo | Inventario por planta/sesión/cultivo, auditoría de `0117`, revisión de cajas y piloto humano; derivados en `outputs/datasets/` | Acuerdo y exclusiones reportados; política de clases congelada o decisión de fusionar/descartar. Dataset original intacto. Esta parte requiere datos humanos que no se pueden inventar |
| M3 — piloto estructural discriminante | `blender_annotations`, `blender_dataset`, cámaras y ambiente; extender fixture de silueta aislada a órgano real, guardar máscaras y morfología por escena | Integridad, presupuesto medido, correspondencia identidad/caja/estado/visibilidad. Comparaciones con mismas semillas y cambios controlados; todas las variantes quedan en el mismo split |
| M4 — migración de consumidores | Un diccionario pasado explícitamente a exportadores/config/validadores; diagnóstico consciente de clases, cabezas de detección/clasificación con ignore real | Fixtures con varias clases y ambiguos, JSON/YAML/labels coherentes. Baseline monoclase sigue reproduciéndose. Android rechaza de forma explícita modelos incompatibles |
| M5 — screening | Comparar protocolo A con real-only y control sintético a igual presupuesto; tres semillas para medir variación, sin test externo | Selección solo desarrollo, tabla de coste y modos de fallo; decisión congelada o descarte. No inferir significancia de tres corridas |
| M6 — confirmación | Congelar ganador, comparadores, clases, datos, hiperparámetros, semillas, recursos y análisis antes de abrir nueva captura independiente | Evaluación una vez según lock, intervalos por unidades de captura e inicialización, resultados negativos preservados; artefacto listo para un manuscrito defendible |

M1 y preparación técnica de M3 pueden avanzar mientras llega la revisión M2; M4 puede usar fixtures, pero no entrenar ni promover etiquetas reales no validadas. El pipeline de color, geometría o cámara que finalmente se promueva requiere la revisión humana de regresión pertinente; el fixture de dos máscaras no la reemplaza.

## Matriz experimental priorizada

Todos los umbrales siguientes son **criterios de ingeniería propuestos para la nueva campaña**, fijados antes de sus resultados y revisables antes del lock por coste o relevancia práctica. No se cambian retrospectivamente para declarar éxito. Las cantidades de fixtures son pruebas de cobertura, no tamaños estadísticos.

| ID | Pregunta / cambio controlado | Comparación y datos | Artefactos, criterio y siguiente decisión |
|---|---|---|---|
| D0 | ¿La evidencia guardada es coherente y recuperable? | Recalcular deltas por semilla y hashes, sin entrenar | Ejecutado: seis pesos y 180 archivos coinciden. Repetir solo si cambia checkout/artefactos o se traslada máquina |
| D1 | ¿Ocupación de caja es oclusión? | Misma silueta/cámara aislada y tapada 50 % | Ejecutado: ocupación idéntica, oclusión 0/0,5. La tasa verdadera exige denominador aislado; extender a cáliz/hojas del modelo |
| D2 | ¿Las clases visuales son observables y reproducibles? | Dos anotadores, originales de desarrollo y renders sin mostrar metadata; submuestra de fruto pareado | Matriz de acuerdo, caja visible/amodal, abstención y minutos. Si la transición no se distingue, fusionar antes de entrenar; si madurez del fruto no es observable, limitar el claim |
| P1 | ¿La señal pequeña/densa procede de tamaño y oclusión? | Cruce mínimo de 3 cámaras y 2 niveles de cobertura, dos semillas base: 12 condiciones de escena; incluir frames contextuales, mantener presupuesto de píxeles/materiales | Guardar RGB/máscara completa/aislada por órgano seleccionado, geometría y tiempos. Cero errores de identidad/clase, cajas válidas, estados recuperables a resolución de detector. No pedir a este piloto demostrar transferencia |
| P2 | ¿El contexto aporta algo más que un proxy de bordes? | Sobre mismas escenas P1, fondo histórico frente a variación contextual, dejando el órgano fijo; registrar negativos sin capacho | Medir borde/luma como diagnóstico y falsos positivos en desarrollo. Si mejoran proxies sin utilidad, no seguir optimizándolos como objetivo. Cambiar fondo no puede alterar GT |
| T1 | ¿Mejora A con igual información/cómputo? | Real-only; real+randomización genérica; real+estructura/visibilidad controlada. Igual subconjunto real, pesos iniciales y pasos; un presupuesto bajo fijado después de M2 | Métrica primaria AP50–95 conjunto por clase en dominio externo, objetivo Δ≥0,02 frente al control sintético y real-only; intervalo de contraste ajustado excluye 0. Por ahora solo screening en desarrollo; sin acceso al test para elegir |
| T2 | ¿Qué componente explica el efecto? | Ablación de cobertura de visibilidad y de desacoplamiento contexto–clase, una a la vez respecto A, mismas escenas/semillas/pasos | Si quitar el componente no reduce el efecto, no reclamar ese mecanismo. Si atajo de fondo/posición predice clase, revisar muestreo. Conservar control de apariencia sin estructura |
| T3 | ¿Ahorra etiquetas reales? | Curvas de presupuestos reales anidados, p.ej. 25/50/100 % tras fijar tamaño y grupos; real-only, referencia clásica comparable, sintético-only, mejor mezcla; preentrenamiento solo si T1 lo justifica | Coste humano total y área bajo curva de aprendizaje. Objetivo secundario ≥25 % menos minutos reales con margen de no inferioridad de AP 0,01. No equivale a ahorrar imágenes si hay más trabajo de adjudicación |
| C1 | ¿Se mantiene en otra captura? | Ganador y comparadores congelados, nueva sesión/fila/cultivo independiente, todos los casos anotados según mismo protocolo | AP, recall operativo, confusiones, cobertura/incertidumbre y coste. Caídas por clase >0,01 en recall al punto operativo acordado bloquean claim integral; reportar tradeoffs |

La referencia clásica pertinente se reutiliza como receta/comparador cuando su responsable pueda proporcionar una versión aplicable; no se usa su métrica monoclase como baseline multiclase. Si la receta no es reproducible, declararlo y usar un baseline convencional explícito y congelado en esta nueva tarea, sin atribuirlo al experimento estudiantil.

No repetir la mezcla v1, luminancia o interpolación originales salvo que cambie una variable informativa. Si se investiga interpolación, agregar control entre dos checkpoints real-only para aislar el efecto. Los sintéticos-only delimitan brecha, no un objetivo obligatorio de sustituir todos los reales.

## Particiones, selección y medición

1. Asignar grupos antes de derivar imágenes: planta, secuencia, sesión y cultivo cuando existan. Vistas correlacionadas, contrafactuales y todas las variantes de la misma escena permanecen en el mismo split. Hash exacto y dHash son filtros, no sustitutos de identidad de adquisición.
2. Los conjuntos históricos son de desarrollo/exploración para esta nueva línea. Una captura nueva, apartada antes de calibrar generador o hiperparámetros, es la evaluación externa. Si no llega, avanzar ingeniería y pilotos, pero no cerrar la confirmación ni denominar “virgen” un test reparado.
3. Generador, anotación humana y entrenamiento tienen semillas/versiones distintas. Usar semillas de escena registradas y seeds de entrenamiento emparejadas entre comparadores; semilla igual no garantiza correspondencia de órganos cuando cambia gramática. Para pares causales guardar una morfología base y aplicar intervenciones declaradas sobre ella.
4. Fijar detector, inicialización por hash, resolución, optimizador real, LR, aumentación online, batch, pasos, política de selección y coste. El control de repetición real iguala actualizaciones y exposición real. Reportar además un presupuesto por tiempo si forma parte de la contribución. `optimizer=auto` no basta como especificación confirmatoria.
5. Métricas: AP50–95 y AP75 por clase y macro; AP colapsado para separar localización; recall por clase a precisión operativa fijada en validación; matriz de confusión con fondos/no detectados; exactitud de clase condicionada a match IoU; errores de centro/tamaño; estratos de tamaño tras resize, oclusión medida, truncamiento y carga. No sumar semillas como si fueran nuevas imágenes independientes.
6. Para incertidumbre, bootstrap emparejado por unidad de captura, incluyendo todas sus imágenes, y variación entre inicializaciones. Conservar conteos y denominadores por estrato. Corrección de multiplicidad para dos contrastes primarios, o jerarquía predefinida control sintético→real-only; fijarlo antes de confirmar. No seleccionar umbrales por test.
7. Tamaños: el piloto estima desviación de diferencias entre seeds y variación entre capturas. Para planificar precisión aproximada usar `n ≈ (1,96*s/h)^2`, ajustando por t de Student, correlación y diseño; no aplicar esa fórmula a AP como garantía universal. Para una tasa binaria, 385 instancias independientes es una referencia de ±5 pp en el peor caso, no una exigencia válida para 385 frutos correlacionados. Elegir sesiones y clases minoritarias por precisión requerida y coste observado.

El screening de tres seeds sirve para descartar fallos grandes y medir variación. La confirmación ampliará seeds y unidades de captura según esa precisión; presupuestar inicialmente cinco, con posible extensión a diez solo bajo una regla y techo definidos antes de ver el holdout. Más seeds no sustituyen más sesiones reales.

## Comandos comprobados y recuperación

Comprobar primero estado del checkout. Si la rama de intervención no está activa y hay cambios ajenos, no ejecutar un switch destructivo, reset ni stash general; inspeccionar y conservarlos. No crear una rama distinta con el mismo nombre si ya existe.

```powershell
Set-Location C:\dev\SyntheticPlantGeneration
git status --short --branch
git rev-parse HEAD
git diff --stat
$env:PYTHONPATH="$PWD\src"
& .venv-training/Scripts/python.exe scripts/validate_repository_context_graph.py
& .venv-training/Scripts/python.exe -m unittest discover -s tests -v
```

La suite completa pasó antes de cambios del núcleo (131 tests) y al cierre de la intervención (140 tests, 112,319 s); también se ejecutaron las pruebas pertinentes de los módulos modificados. El log final está en `outputs/audits/scientific_route_20260908/final_tests.log`. En continuidad volver a ejecutar la suite si el nuevo diff lo justifica. No instalar paquetes solo para conseguir que `python` resuelva en PATH: usar el intérprete disponible mostrado arriba o descubrir uno equivalente.

Para recomputar evidencia histórica, sin evaluación nueva de modelos:

```powershell
& .venv-training/Scripts/python.exe scripts/audit_scientific_evidence.py --output outputs/audits/scientific_route_20260908/evidence.json
```

El script lee labels originales y artefactos existentes, verifica pesos/piloto y recalcula deltas; no mide de nuevo AP desde predicciones. Si los outputs faltan en otra máquina, recuperar artefactos privados por un canal autorizado o registrar la limitación. No fabricar resultados a partir de los números del README.

Preparación de observaciones —ya ejecutada, no sobrescribe revisiones existentes—:

```powershell
& .venv-training/Scripts/python.exe scripts/prepare_instance_observation_review.py --manifest outputs/datasets/uchuva_virtual_fidelity_v2_pilot_seed_16000/manifest.jsonl --output outputs/audits/scientific_route_20260908/instance_observations.jsonl
```

Si existe el output, leerlo; para otra derivación elegir un nombre nuevo. La negativa a sobrescribir evita perder anotación humana. El SHA del manifiesto fuente queda en cada fila. Aún falta una herramienta de importación/adjudicación humana; no confundir este comando con etiquetado terminado.

Smoke Blender ya ejecutado:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --factory-startup --python-exit-code 1 --python scripts/blender_annotation_contract_smoke.py
```

Produce dos máscaras y `outputs/audits/scientific_route_20260908/blender_smoke/report.json`. Es una fixture técnica de esfera/oclusor, no una modificación del modelo botánico. Antes de repetir y conservar una comparación, copiar su pequeño reporte/máscaras a otro directorio de outputs o parametrizar la salida; esta fixture usa ruta fija y no es un runner de campañas.

No se dan comandos inventados para T1/C1: el runner multiclase todavía debe implementarse/adaptarse y superar M1–M4. Los comandos históricos `run_hybrid_training.py` evalúan test durante su ejecución y no son el lanzador confirmatorio nuevo. No invocarlos como siguiente paso automático.

## Coste y límites de lanzamiento

El único coste nuevo medido de render fue 18,437 s para dos pases de 128×128. No se extrapola linealmente a cultivos de veinte plantas o imágenes de 1280 px. Las 180 verificaciones de archivos no equivalen a regenerar el piloto.

Los antecedentes clásicos registran aproximadamente 20–30 min por corrida de 50 épocas en ejecuciones continuas, con suspensiones y resumes que contaminan otras duraciones. Es una referencia histórica monoclase. Una campaña de 6 condiciones × 5 seeds representaría orientativamente 10–15 horas solo de entrenamiento si se mantuviera ese coste; no es un presupuesto aprobado ni una estimación válida sin el piloto multiclase.

Antes de P1 medir **una escena real del generador**, guardar tiempo de construcción, auditoría, RGB y máscaras, pico de RAM/VRAM, bytes y tasa de rechazo. Ejecutar una sola instancia de Blender, reserva de RAM≥4 GiB y límite técnico acotado por proceso. Si supera el techo de la sesión o falla memoria, preservar log/entrada, reducir resolución para diagnosticar y mantener pendiente la aceptación a resolución final. No rebajar tests físicos para “pasar” el piloto.

La campaña grande exige una estimación `tiempo por candidato × candidatos por aceptado × escenas`, más validación, entrenamiento, almacenamiento y horas humanas. El presupuesto debe expresar estos costes y un techo de ejecución. Sin techo autorizado, continuar con código, fixtures y preparativos; no lanzar el lote de 640 ni entrenamientos nocturnos por inercia.

Recuperación: cada escena/entrenamiento tendrá config sellada, lock de único proceso, staging y promoción atómica. Quarantinar fallos/duplicados por nombre nuevo, conservar logs, checkpoints y manifiestos; no eliminar la carpeta mala hasta preservar evidencia. Verificar secuencia exacta de épocas sin duplicados al reanudar. La protección de config añadida aquí no detecta todavía cambios de contenido en un perfil ubicado en la misma ruta: M1 debe cubrirlos.

## Reglas para continuar, pivotar o descartar

- Si las clases no alcanzan acuerdo útil, revisar protocolo o fusionarlas antes de M4; no compensarlo con pseudoetiquetas automáticas.
- Si el fruto oculto no permite inferencia fiable con RGB, informar ese límite y sostener solamente la tarea de estado visual. Una publicación agronómica requerirá evidencia adicional.
- Si las máscaras/identidades fallan, detener generación y corregir integridad; no entrenar para “ver si funciona”.
- Si T1 no mejora al control de igual cómputo, no ampliar campañas: analizar estratos y testar solo la explicación apoyada por evidencia. Si mejorar apariencia es la explicación restante, evaluar B en un piloto con auditoría de etiquetas; no adoptar difusión por novedad.
- Si el efecto desaparece en C1, publicar/reportar el resultado negativo según su valor y precisión; volver a desarrollo requerirá otro holdout para una afirmación confirmatoria futura.
- Un intervalo amplio implica evidencia insuficiente, no victoria ni refutación. Un efecto pequeño pero bien estimado exige reformular la relevancia, no cambiar el criterio después de verlo.

## Registro vivo

Actualizar esta sección al cerrar cada intervención: fecha, HEAD/diff, comando, artefacto, resultado, decisión y próximo hito. Las métricas detalladas van en outputs y el resumen versionable aquí; no duplicar una bitácora en cinco archivos.

| Fecha | Progreso / sorpresa | Resultado y pendiente |
|---|---|---|
| 2026-09-08 | Documento de encargo leído íntegro desde Downloads; GitHub y checkout contrastados | Commit de corte confirmado; rama creada; 12 cambios ajenos rastreados y reporte no rastreado preservados |
| 2026-09-08 | Descubierto estudio posterior con test ya ejecutado | +0,001533 AP medio, 2/3 seeds negativas; seis hashes de pesos coinciden. Se corrigió interpretación del README |
| 2026-09-08 | Inventario real y piloto | 0117 sin label; 180/180 archivos del piloto coinciden; 38 escenas de una planta y 22 de dos; máscaras históricas descartadas |
| 2026-09-08 | Tests baseline | Sin PYTHONPATH: fallo de importación conservado. Con src: 131 tests OK, 90,457 s. No entrenamiento nuevo |
| 2026-09-08 | Contrato y observaciones | Seis tests nuevos OK, 151 registros pendientes creados; clases reales y madurez siguen sin validar |
| 2026-09-08 | Prueba nueva de oclusión Blender | Dos pases EEVEE en 18,437 s. Misma ocupación 0,780273 con oclusión 0/0,5; resultado técnico, no ensayo de transferencia |
| 2026-09-08 | Reanudación del dataset | Se rechaza config cambiada antes de escribir. Dos tests de integridad y doce helpers OK; hashes de entradas/fuente pendientes M1 |
| 2026-09-08 | Grafo e instrucciones | Corrección de autoridad externa y rutas; cuatro tests del grafo OK; validador 130 nodos/237 aristas. Permisos históricos alineados con encargo |
| 2026-09-08 | Verificación de cierre | Suite completa: 140 tests OK en 112,319 s. Los once archivos ajenos fuera del grafo conservan SHA-256; reconstruir el grafo sin nuestras tres ediciones coincide con su hash inicial. Evidencia en `final_tests.log` y `preexisting_preservation_check.json` |
| Siguiente | **M1** más preparación de **M2/M3** | No pedir entrevista general. Obtener anotación/captura humana solo al llegar a dependencia indispensable; avanzar fixtures/procedencia en paralelo lógico, sin delegación requerida |

La intervención termina con auditoría y primera base implementadas, validación técnica ejecutada y campaña científica pendiente. No se ha confirmado la hipótesis, migrado el entrenamiento a multiclase ni aprobado visualmente el cultivo. No se han fusionado ni publicado los cambios.

## Texto exacto de arranque

Copiar este texto en una tarea de Codex abierta sobre el repositorio:

```text
Continúa la intervención científica de Blender en C:\dev\SyntheticPlantGeneration.
Lee AGENTS.md y el grafo; después lee íntegramente
docs/plan_auditoria_cientifica_blender_2026-09-08.md y su auditoría enlazada.
Verifica rama, HEAD, git status y diff contra el corte registrado; preserva
los cambios ajenos de Android y del grafo. Revisa el registro vivo y outputs.
M0 está ejecutado: continúa implementando y probando M1 y preparando M2/M3.
Respeta las autorizaciones, límites y validaciones humanas del plan;
no repitas la entrevista ni presentes madurez o resultados no validados como hechos.
Actualiza el registro vivo para la siguiente continuidad.
```
