# Generador actual y reutilización desde Gazebo

La arquitectura sigue siendo **árbol morfológico → validación → intérprete**.
`src/uchuva_lsystem/` define la planta; Blender genera y audita mallas.
`src/uchuva_gazebo/admitted_plants.py` entrega el mismo árbol completo al
consumidor Gazebo, conservando IDs, posturas nodales, metadatos y procedencia.
El prototipo geométrico legado no define la arquitectura.

## Versiones y responsabilidades

- `trained_trellis_nodal_repulsion_v8`: arquitectura nodal, copa ramificada,
  reproducción derivada del desarrollo y capachos colgantes. Sus ángulos y
  ajustes de ingeniería no son mediciones botánicas ni una norma.
- `nodal_repulsion.py`, `nodal_chain_candidates.py` y los intérpretes
  `blender_nodal_*`: búsqueda de posturas desde abajo, priorizando descensos,
  sin usar el encuadre para ocultar contactos.
- `spatial_admission.py`: admisión reversible de órganos completos cuando
  resulta necesaria, con pérdidas **estrictamente menores del 5 %** para
  frutos, número de hojas y proxy nominal foliar largo×ancho, cada uno sobre
  el original. No se reinician cuotas entre intentos ni se reducen dimensiones.
- `reproductive_orientation.py` y `organ_frames.py`: dirección colgante y
  marcos compartidos entre geometría y proxies.
- `cultivation_floor.py` / `blender_cultivation_floor.py`: plan reproducible
  de tierra, manchas húmedas/secas, hojarasca y vegetación irregular. El
  contexto no modifica los árboles admitidos. Es una heurística visual; no
  certifica todas las interacciones del suelo y maleza.

Las clases siguen describiendo apariencia del capacho; no prueban madurez
fisiológica del fruto. La preparación del contexto y las capturas no crean
frutos ni hojas para satisfacer cuotas de imagen.

## Generar la morfología en Python puro

No necesita Blender, Gazebo ni dependencias nuevas:

```powershell
python scripts/generate_morphology_tree.py --seed 73 --preset trained_trellis_nodal_repulsion_v8 --phenology-model literature_cohort_v1 --no-resolve-growth --output outputs/specs/raw_73.json --validation-output outputs/specs/raw_73_validation.json
```

Este resultado es **morfología previa a la admisión física**. Una validación
morfológica sin errores no equivale a cero cruces de las mallas finales.
La API equivalente es `uchuva_lsystem.grammar.generate_morphology_tree()`.
Los valores por defecto de la CLI conservan el comportamiento histórico.

La búsqueda/admisión Blender reutilizable está en `worker_spatial_pool.py`:
consume un `job.json`, una configuración explícita de campaña y su lock de
fuentes. Conserva original, intentos, posturas, plan reversible y auditorías.
`run_spatial_plant_pool.py` es su controlador secuencial; no se debe reanudar
una campaña histórica con hashes distintos. Los contratos de configuración
y control se describen en [la guía de admisión](plantas_admision_espacial_8h.md).

Para preparar una ejecución nueva sin rutas históricas ni copiar una campaña:

```powershell
python scripts/prepare_spatial_plant_pool.py --root outputs/mi_admision --seed 73 --blender "C:/Program Files/Blender Foundation/Blender 5.1/blender.exe" --hours 1
python scripts/run_spatial_plant_pool.py outputs/mi_admision
```

La preparación no lanza Blender. Congela fuentes, configuración y cola nueva;
el reloj efectivo comienza al prepararla. Las previsualizaciones están
desactivadas: la salida principal son árboles y auditorías, con rechazos
preservados. La cola recorre semillas nuevas hasta agotar el tiempo. Nunca
ejecutar esta segunda orden sobre la campaña actual de veinte plantas, cuya
fase de generación ya terminó.

## Exportar una planta admitida para otro consumidor

```powershell
python scripts/export_admitted_plant.py --plant RUTA/plant.json --audits RUTA --metres-per-scene-unit 0.1 --lod 1 --output outputs/gazebo/plant_bundle.json
```

`RUTA` contiene `admission.json`, `final_independent_mesh.json`, `ground.json`
y `orientation.json`. Se comprueban anatomía e identidad del árbol, límites
de pérdida, ausencia de cruces duros, suelo y orientación. El archivo contiene
el árbol completo, el plan semántico Gazebo y los hashes de las evidencias.
No sobrescribe un bundle anterior. Se puede cargar sin instalar Blender:

```python
import json
from uchuva_lsystem.morphology import Plant

bundle = json.load(open("outputs/gazebo/plant_bundle.json", encoding="utf-8"))
plant = Plant.from_dict(bundle["plant"])
metres_per_scene_unit = bundle["scene_units"]["metres_per_scene_unit"]
# El intérprete conserva plant.metadata y la receta de posturas nodales.
```

La conversión de unidades es obligatoria y explícita. `0.1` corresponde a la
escena de admisión actual; no debe trasladarse automáticamente al exportador
histórico de ocho unidades por metro. No se reescalan ni reinterpretan los
órganos al construir el bundle.

El bundle verifica evidencia estática suministrada por el llamador; no realiza
una nueva auditoría de colisiones en Gazebo. No añade masas, articulaciones,
rigidez, desprendimiento ni una simulación dinámica validada. El plan Gazebo
mantiene sus niveles LOD y limitaciones; el JSON morfológico es la fuente para
una futura reconstrucción de geometría, no una nueva arquitectura vegetal.

## Comprobaciones

Las pruebas puras cubren regeneración, admisión y reversibilidad, orientación,
marcos, presupuesto, contexto reproducible y contrato Gazebo. Los probes
`tests/blender_*` comprueban la interpretación cuando Blender está disponible.
Cada planta y cada escena deben disponer además de su auditoría efectiva de
malla, suelo y unión; un fixture no admite por sí solo una nueva semilla.

No se versionan imágenes generadas, pesos, campañas bajo `outputs/`, PDFs
descargados ni materiales brutos. Los recursos CC0 existentes conservan su
manifiesto y licencia. El grafo distingue los diez errores anteriores de
localizadores de cualquier regresión nueva.

## Reanudar sólo el dataset congelado

Después de completar la transición de veinte plantas, no se vuelve a detener
la fase histórica de plantas: sus PIDs pueden haber sido reutilizados por
otros procesos, incluso protegidos. `resume_spatial_dataset.py RAIZ REVISION`
comprueba el pool y sus auditorías, los hashes de datos/fuentes y su propio
`dataset_resume_source_lock.json`, sin consultar ni tocar esos PIDs antiguos.
El lock contiene `controller_sha256` y `dataset_source_lock_sha256`; debe
prepararse como revisión explícita tras preservar evidencias y comprobar que
no queda otro controlador o trabajador propio activo.

El supervisor posee únicamente los nuevos hijos Blender. Los recicla después
de cada bloque de 24 imágenes completas para acotar memoria retenida, conserva
los pares ya comprometidos y archiva sólo escenas nuevas sin vistas completas
antes de reconstruirlas. Todo traslado se comprueba dentro de la raíz de la
campaña. La receta de generación, órganos, anotaciones y reloj efectivo no
cambian; no se amplía tiempo por una recuperación. Cada ciclo conserva
identidad, stdout, stderr y motivo de salida en `dataset_process_cycles/`.

La ejecución del 29/10 quedó cerrada con 144 pares, veinte árboles visibles y
sin entrenamiento. El [informe verificable](../reports/dataset_cultivo_admitido_2026-10-29.md)
explica la integridad de anotaciones y las brechas que deben controlarse antes
de utilizar estas vistas en un piloto de aumentación.

## Captura optimizada y benchmark emparejado

La ruta histórica permanece intacta. `render_spatial_dataset_optimized.py`
es una entrada nueva que recibe campaña fuente, salida independiente,
segundos efectivos y máximo de imágenes explícitos. No debe apuntar a una
campaña cerrada ni ejecutarse como una ampliación implícita de su presupuesto.
Produce una escena por proceso para conservar el límite de memoria; al
reanudar la misma salida conserva su reloj nativo y lock de fuentes.

`CaptureSession` conserva resolución 960×720, Cycles/OptiX, doce muestras,
denoising, materiales y el rasterizador exacto de máscaras sin antialiasing.
Reutiliza luces/nodos, registro de instancias y colores de IDs; falla si un
material RGB lee Object Info Color, incluidos grupos anidados. Los demás
objetos siguen presentes como oclusores negros. No descarta órganos ni
etiquetas por distancia. El fingerprint binario lee coordenadas completas,
topología y transformaciones antes y después de cada vista; no usa una
muestra ni un hash cacheado de geometría. El hash histórico completo permanece
como comprobación de entrada y salida de la escena. Los dos formatos de hash
son distintos y no se presentan como equivalentes.

`mask_arrays.py` acelera cuantización y estadísticas con el NumPy ya incluido
en Blender, sin instalar dependencias. Conserva redondeo en doble precisión,
colores desconocidos mediante la regla histórica, tolerancia, desempate,
transparencia y cajas por extremos de píxeles. Si NumPy no está disponible o
se pide retirar componentes pequeños, delega al rasterizador histórico.

`CaptureJournal` compromete `view.json` individualmente y actualiza un índice
pequeño. `committed_views()` sigue siendo compatible; el manifiesto completo
se consolida al terminar la escena, evitando reescribir todas las instancias
en cada toma. Los pares existentes no se sobrescriben. Un fallo entre commit
e índice se recupera leyendo los registros individuales.

La semilla de condiciones de captura es independiente de la arquitectura,
clases y cámara. Alterna los perfiles diagnósticos existentes de campo,
difusa y sombra, con variación moderada de azimut, elevación y exposición.
Son heurísticas explícitas, no una medición de iluminación del cultivo. La
configuración efectiva se guarda por vista; los materiales revisados no se
recalibran en esta optimización.

`benchmark_spatial_capture.py` reconstruye una escena de la campaña fuente y
repite su auditoría física completa antes de guardar un `.blend`. Ambas rutas
reabren ese mismo archivo con tres cámaras y condiciones idénticas. El
reporte `report_capture_benchmark.py` informa igualdad estricta de píxeles
RGB/máscara, instancias, clases, cajas, YOLO, cámara y luz. El cierre adicional
conserva exactas las anotaciones y separa una equivalencia numérica RGB de
máximo 1/255 y error absoluto medio ≤0,001 niveles de byte por canal. Ese
criterio es de ingeniería, no una tolerancia botánica o física. Se realiza
además una repetición del método original para observar su propia variación.
Un RGB que difiere no se declara idéntico bit a bit. Mide tiempo nativo que excluye
suspensión, separando preparación, render, máscaras, controles e I/O. El
pronóstico conserva la auditoría de cada escena y el reciclado cada 24 vistas;
tres vistas de una escena no proporcionan un intervalo de confianza.

Un hash calculado antes de serializar no se da por válido automáticamente al
reabrir el `.blend`. Si difiere, se preserva el intento y se detiene la captura.
`audit_saved_capture_scene.py` comprueba invariancia de cámara y repite malla,
suelo y orientación sobre el archivo recargado, sin relajar tolerancias. Sólo
entonces se fija un nuevo hash exacto posterior a la recarga para ambas rutas,
conservando el anterior como procedencia. No se atribuye la diferencia a una
causa numérica concreta sin aislarla. Una discrepancia entre métodos después
de fijar esa referencia sigue siendo un fallo, no una normalización admitida.

En el ensayo se identificó la caché de `matrix_world` de frutos internos
ocultos al recargar: no entran en el grafo de viewport hasta ser evaluados.
`refresh_hidden_fruit_transforms()` usa el mismo ciclo de visibilidad temporal
del auditor de suelo y restaura los flags, sin cambiar `hide_render`, mallas
o canales de transformación. Así vuelve a coincidir el hash exacto posterior
a la auditoría; los intentos anteriores quedan preservados.

### Escenas compartidas y caché de Cycles

`render_spatial_dataset_persistent.py` selecciona explícitamente
`DualSceneCaptureSession` y fija sus fuentes en un lock nuevo. RGB conserva
Cycles con datos persistentes; otra escena Workbench comparte **todos** los
objetos y colecciones, incluidos oclusores, sin copiar ni simplificar
geometría. Sus ajustes de color son independientes de RGB. La comparación
real de tres vistas exige máscaras/etiquetas exactas y el criterio RGB
publicado; no se debe confundir ese ensayo con un entrenamiento.

La variante conserva una escena por proceso. Un supervisor de producción debe
reciclar cada bloque completo y vigilar el límite efectivo, sin reabrir el
presupuesto de una campaña cerrada. Presupuesto y máximo se pasan expresamente
a una **salida nueva**; reanudar no permite cambiarlos. La caché requiere
memoria adicional: tres vistas no certifican por sí solas el pico de RAM de
una campaña larga.

La planificación `balanced_depth_light/2` asigna campo/difusa/sombra a todas
las profundidades dentro de cada escena, con cantidades equilibradas. Evita
acoplar permanentemente un ciclo de tres luces al de tres distancias. Conserva
la semilla independiente, variaciones moderadas y perfiles/materiales existentes.
Las pruebas puras comprueban ese balance.

Si cambia el rendimiento del equipo durante un benchmark, se repiten la
referencia y la preparación: la aceleración del sistema no se atribuye al
código. `run_matched_capture_benchmark.py` reconstruye los mismos árboles y
repite las tres vistas originales antes de proyectar tiempos con
`summarize_capture_optimization.py`.

La política de tamaño de entrenamiento se aplica sobre una derivación
explícita, conservando máscara y metadatos completos. El exportador histórico
contiene filtros de lado mínimo de 6 píxeles y 24 píxeles visibles. Esos valores
no se deben atribuir automáticamente al entrenador factorial, cuya captura
conserva incluso fragmentos de un píxel. Una continuación debe congelar el
filtro vigente, su convención de resolución y la política de regiones
ignoradas antes de entrenar; no basta borrar cajas del RGB para declarar
correcto un conjunto de entrenamiento.
