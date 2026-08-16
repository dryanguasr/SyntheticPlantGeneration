# Generador procedural morfológico de uchuva

La ruta experimental vigente añade crecimiento multi-planta sincronizado,
trellis continuo previo al crecimiento, política de contacto por pares,
procedencia canónica y métricas A–F. La arquitectura y los comandos de
reproducción están documentados en
[`docs/arquitectura_multi_planta_sincronizada.md`](docs/arquitectura_multi_planta_sincronizada.md).

Proyecto experimental para construir un generador procedural de plantas de **uchuva** (*Physalis peruviana*) orientado a datos sintéticos para visión por computador y robótica agrícola.

El proyecto parte de un prototipo geométrico en Blender (`planta_procedural_v05.py`), pero la dirección actual ya no es refinar una planta genérica. El objetivo es migrar hacia un **modelo morfológico-paramétrico basado en L-System**, donde la geometría se derive de una arquitectura botánica explícita: eje principal, ramas, entrenudos, nodos, hojas, yemas axilares, pedicelos, cáliz/capacho y fruto.

---

## Estado actual

El repositorio debe considerarse en etapa de transición:

```text
prototipo procedural genérico
        ↓
modelo morfológico de uchuva
        ↓
generador de escenas sintéticas anotables
```

La versión `planta_procedural_v05.py` contiene utilidades valiosas para Blender, pero **no debe tratarse como arquitectura botánica definitiva**.

Se puede rescatar de esa versión:

- limpieza de escena y data-blocks;
- creación de materiales;
- creación de cilindros entre puntos;
- generación de hojas simples como malla;
- creación de frutos, cáliz simplificado y pedúnculos;
- configuración de cámara y luz;
- exportación de especificaciones a JSON.

Pero la arquitectura futura debe partir de:

```text
árbol morfológico → interpretación geométrica en Blender
```

no de:

```text
órganos puestos manual/proceduralmente alrededor de un tallo
```

---

## Objetivo científico-técnico

Construir un generador sintético de uchuva que sea:

1. **Botánicamente defendible:** los órganos deben surgir de una gramática coherente con la morfología de la uchuva.
2. **Paramétrico:** cada escena debe poder reproducirse mediante semilla y parámetros.
3. **Anotable:** los frutos, cálices/capachos, hojas y órganos relevantes deben poder exportarse con metadatos.
4. **Útil para visión robótica:** la variación debe ayudar a entrenar o evaluar detectores bajo oclusión, madurez variable, presencia de cáliz y condiciones visuales diversas.
5. **Extensible:** el pipeline debe poder crecer hacia generación por lotes, máscaras, bounding boxes y formatos YOLO/COCO.

---

## Rasgos de uchuva que guían el modelo

El modelo debe representar, al menos de forma inicial:

- planta herbácea/sufruticosa, erecta o ascendente, ramificada;
- crecimiento por nodos y entrenudos;
- hojas pecioladas, ovadas/ovado-cordadas/deltadas, con margen variable;
- yemas axilares;
- flores/frutos solitarios axilares;
- pedicelo corto que se alarga en fruto;
- cáliz persistente e inflado que envuelve o acompaña al fruto;
- mezcla de estados fenológicos en una misma planta;
- fruto representado en el arbol morfologico y, en la iteracion actual,
  oculto por capachos cerrados.

---

## Arquitectura esperada del repositorio

Estructura recomendada:

```text
.
├─ README.md
├─ AGENTS.md
├─ .gitignore
│
├─ docs/
│  ├─ checkpoint_blender_uchuva_lsystem_03.md
│  ├─ modelo_morfologico_inicial_uchuva.md
│  ├─ referencias_uchuva_lsystem.bib
│  └─ decisiones_tecnicas.md
│
├─ src/
│  └─ uchuva_lsystem/
│     ├─ __init__.py
│     ├─ grammar.py
│     ├─ morphology.py
│     ├─ parameters.py
│     ├─ blender_geometry.py
│     ├─ blender_scene.py
│     ├─ exporters.py
│     └─ validation.py
│
├─ scripts/
│  ├─ generate_single_plant.py
│  ├─ generate_batch.py
│  └─ run_blender_background.ps1
│
├─ examples/
│  ├─ morphology_tree_seed_0.json
│  └─ plant_specs_seed_0.json
│
├─ legacy/
│  └─ planta_procedural_v05.py
│
└─ outputs/
   ├─ specs/
   ├─ renders/
   ├─ masks/
   └─ annotations/
```

La carpeta `outputs/` debe quedar ignorada por Git.

---

## Módulos propuestos

### `morphology.py`

Define las entidades del árbol morfológico:

- `Plant`
- `Axis`
- `Internode`
- `Node`
- `Leaf`
- `AxillaryBud`
- `Branch`
- `Pedicel`
- `Calyx`
- `Fruit`
- `ReproductiveUnit`

Debe priorizar `dataclasses` serializables a JSON.

---

### `grammar.py`

Contiene reglas de generación tipo L-System/morfología procedural:

```text
Apex → Internode + Node + Apex
Node → Leaf + AxillaryBud
AxillaryBud → DormantBud | Branch | ReproductiveUnit
ReproductiveUnit → Flower | YoungFruitWithCalyx | MatureFruitWithCalyx | ExposedFruit
```

La primera versión debe ser simple y reproducible por semilla.

---

### `parameters.py`

Centraliza rangos y presets:

- altura de planta;
- longitud de entrenudos;
- radio de tallos por orden;
- ángulos de bifurcación;
- tamaño de hoja;
- relación largo/ancho;
- longitud de pecíolo;
- longitud de pedicelo;
- tamaño del fruto;
- relación cáliz/fruto;
- probabilidad de ramificación;
- probabilidad de unidad reproductiva;
- mezcla fenológica.

Los parámetros deben distinguir entre:

```text
documentado
medido
estimado
supuesto temporal
```

---

### `blender_geometry.py`

Traduce módulos morfológicos a geometría:

- cilindros/curvas para tallos, ramas, pecíolos y pedicelos;
- hojas como mallas;
- frutos como mallas simples;
- cáliz/capacho simplificado;
- futura geometría ribada del cáliz.

---

### `blender_scene.py`

Gestiona:

- limpieza de escena;
- materiales;
- cámara;
- luces;
- configuración de render;
- salida de imágenes.

---

### `exporters.py`

Exporta:

- `morphology_tree_seed_X.json`;
- `plant_specs_seed_X.json`;
- `metadata_seed_X.json`;
- más adelante, YOLO/COCO.

---

### `validation.py`

Debe implementar reglas de validez:

- órganos conectados a nodos;
- frutos axilares;
- cáliz asociado al fruto;
- jerarquía de órdenes de ramas;
- radios decrecientes por orden;
- escalas relativas plausibles;
- colisión geométrica vs oclusión visual plausible.

---

## Gramática conceptual inicial

```text
Axiom:
Apex(order=0, age=0)

Rules:
Apex(order, age)
  → Internode(order, length, radius)
    Node(order, node_id, age)
    Apex(order, age+1)

Node(order, node_id, age)
  → Leaf(length, width, petiole, shape, margin, angle)
    AxillaryBud(order, state)

AxillaryBud(order, state)
  → DormantBud
  | Branch(order+1, angle, vigor)
  | ReproductiveUnit(stage)

ReproductiveUnit(stage)
  → Flower
  | YoungFruitWithCalyx
  | MatureFruitWithCalyx
  | ExposedFruit
```

---

## Criterios de validez morfológica

Una escena debe rechazarse o marcarse con advertencias si:

- los frutos no nacen de nodos o axilas;
- las hojas aparecen sin relación con nodos;
- los pedicelos no conectan una axila con un fruto/cáliz;
- el cáliz no acompaña al fruto;
- todos los órganos reproductivos tienen el mismo estado artificialmente;
- las ramas no respetan jerarquía;
- los radios no decrecen por orden de rama;
- la escala hoja–fruto–cáliz queda fuera de rango;
- hay colisiones imposibles entre fruto/cáliz/hoja;
- la escena parece una planta genérica, tomate o pimentón, no uchuva.

---

## Plan de trabajo recomendado

### Fase 0 — Migración del prototipo

- Crear estructura del repo.
- Mover `planta_procedural_v05.py` a `legacy/`.
- Crear módulos vacíos/documentados.
- Crear `.gitignore`.
- Conservar JSONs y renders fuera de Git o en `examples/` solo si son pequeños.

### Fase 1 — Documento morfológico

Crear `docs/modelo_morfologico_inicial_uchuva.md` con:

- rasgos botánicos confirmados;
- parámetros por documentar;
- tabla de parámetros;
- gramática conceptual;
- criterios de validez;
- clases anotables para visión.

### Fase 2 — Árbol morfológico

Implementar `morphology.py`, `parameters.py` y `grammar.py`.

Resultado mínimo:

```text
seed → morphology_tree_seed_X.json
```

### Fase 3 — Intérprete Blender

Conectar el árbol morfológico a Blender.

Resultado mínimo:

```text
morphology_tree_seed_X.json → escena Blender simple
```

### Fase 4 — Validación y anotaciones

Agregar:

- reporte de validación por escena;
- bounding boxes;
- máscaras;
- clases visuales: caliz/capacho cerrado y, en una fase posterior, fruto
  visible o parcialmente visible si se decide abrir capachos.

---

## Ejecución en Blender

Durante el desarrollo, los scripts pueden ejecutarse desde el editor de Blender.

Más adelante se recomienda correr en modo background, por ejemplo en Windows:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python scripts\generate_single_plant.py
```

Ajustar la ruta local según la instalación.

---

## Política de desarrollo

- No refinar estética genérica si no mejora validez botánica o utilidad para visión.
- Mantener funciones pequeñas y testeables.
- Separar generación morfológica de geometría Blender.
- Registrar siempre `seed`, parámetros y versión del script.
- Preferir JSON legible para depuración.
- Evitar dependencias externas al inicio, salvo que sean claramente necesarias.
- No crear datasets masivos hasta tener validación morfológica mínima.
- Mantener `legacy/planta_procedural_v05.py` como referencia, no como base arquitectónica.

---

## Pregunta de investigación emergente

> ¿Cuánto aporta una generación sintética morfológicamente parametrizada de uchuva al entrenamiento y evaluación de modelos de percepción para robótica agrícola, especialmente bajo oclusión, variación de madurez y presencia de cáliz/capacho?

---

## Licencia

Pendiente por definir.

---

## Migracion estructural inicial

La estructura base del proyecto separa la morfologia de la interpretacion en
Blender:

```text
src/uchuva_lsystem/morphology.py
src/uchuva_lsystem/parameters.py
src/uchuva_lsystem/grammar.py
src/uchuva_lsystem/blender_geometry.py
src/uchuva_lsystem/blender_scene.py
src/uchuva_lsystem/exporters.py
src/uchuva_lsystem/validation.py
```

Para generar el primer arbol morfologico sin Blender:

```powershell
python scripts\generate_single_plant.py --seed 0
```

El resultado esperado es:

```text
outputs/specs/morphology_tree_seed_0.json
outputs/specs/validation_report_seed_0.json
```

El prototipo `planta_procedural_v05.py` fue recuperado desde el Text Block de
`legacy/planta_code_01.blend` y se conserva como referencia en `legacy/`.

Para generar una escena `.blend` de previsualizacion desde la gramatica
morfológica actual:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" `
  --background `
  --python scripts\generate_blender_plant.py `
  -- --seed 0
```

El resultado se guarda en:

```text
outputs/blends/uchuva_lsystem_seed_0.blend
```

La capa de planta individual se mantiene separada de la escena de cultivo.
La escena genera todas las plantas, ejecuta una relajación morfológica conjunta
por vecinas, luz, carga reproductiva y tutores, y solo entonces crea geometría.
Los contratos serializables están en:

```text
src/uchuva_lsystem/scene.py
```

El capacho v2 usa un perfil compacto `lantern_squash` de cinco paneles, con
relación alto/ancho 1.15--1.55. Las costillas solo modifican levemente la
silueta; las diez líneas vasculares y su retícula se representan con mapas 2D.
Los estados continúan cerrados y el fruto permanece oculto en la estructura
morfológica.

Para generar una escena de cultivo con 10 plantas:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" `
  --background `
  --python scripts\generate_blender_scene.py `
  -- --seed 0 --plant-count 10 --collision-policy canopy_permissive
```

El resultado se guarda en:

```text
outputs/blends/uchuva_scene_seed_0.blend
outputs/scenes/cultivation_scene_seed_0.json
outputs/scenes/validation_scene_seed_0.json
```

La escena oculta los `Empty` de instancia y aplica las transformaciones a los
objetos para evitar lineas de relacion visibles en Blender. La iluminacion se
genera como luz exterior lejana y reproducible por semilla.

### Ejecucion desde script interno del `.blend`

El archivo `outputs/blends/uchuva_scene_seed_0.blend` incluye un Text Block
autocontenido llamado:

```text
RUN_UCHUVA_SCENE_INTERNAL.py
```

Para regenerar la escena sin depender del repositorio local, abrir ese Text
Block en el editor de texto de Blender y ejecutar `Run Script`. El script
tambien crea reportes internos como Text Blocks:

```text
uchuva_scene_report.json
uchuva_validation_report.json
```

Si el codigo fuente cambia, se puede volver a insertar la version actual dentro
del `.blend` con:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" `
  --background outputs\blends\uchuva_scene_seed_0.blend `
  --python scripts\embed_internal_blend_script.py
```

## Piloto contextual anotable

El preset `annotation_foreground_pilot` crea una planta objetivo y tres vecinas
parciales sobre terreno agricola, con vegetacion generica de fondo. La
morfologia individual sigue viniendo del arbol L-System; el entorno no agrega
organos de uchuva arbitrarios.

El piloto usa cuatro archivos CC0 a 2K de Poly Haven: el material `Brown Mud`
para el suelo y el HDRI `Farmland Overcast`. Sus URLs, licencias y hashes estan
en `src/uchuva_lsystem/blender_environment.py`. Para descargarlos y verificarlos:

```powershell
python scripts\download_cc0_assets.py
```

Para generar una unica escena con tres perfiles de camara, RGB EEVEE/Cycles y
mascaras:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" `
  --background `
  --python scripts\generate_annotation_pilot.py `
  -- --seed 0 --neighbor-count 3
```

La salida queda en:

```text
outputs/pilots/uchuva_annotation_seed_0/
  annotations.json
  scene.json
  scene_validation.json
  robot_close_oblique/
  human_oblique_mid/
  context_wide/

outputs/blends/uchuva_annotation_pilot_seed_0.blend
```

Cada camara exporta `rgb_eevee.png`, `rgb_cycles.png`, mascara semantica,
mascara de instancia de planta y mascara de instancia reproductiva. Las clases
son `background`, `soil`, `leaf`, `stem`, `flower` y `calyx`; el fruto oculto
por capachos cerrados no recibe pixeles de anotacion.

El `.blend` empaqueta los cuatro assets y contiene el Text Block
`RUN_UCHUVA_ANNOTATION_PILOT.py`. Al ejecutarlo desde Blender, el piloto se
regenera sin importar codigo ni imagenes desde rutas externas.

## Dataset piloto real-matched YOLO / MakeSense

La iteracion actual usa `Dataset Original/` como referencia de solo lectura.
El contrato de deteccion tiene una unica clase: `0 = calyx`. Los estados
verde, pajizo y seco se conservan como metadatos en `manifest.jsonl`; las
flores no generan cajas y los frutos permanecen ocultos dentro de capachos
cerrados y opacos.

Primero se construye el perfil cuantitativo real y la comparacion con el
piloto anterior:

```powershell
python scripts\compare_real_synthetic.py
```

El reporte queda en `outputs/domain_analysis/real_vs_synthetic/` y registra
distribuciones globales y por split, luminosidad, orientacion, areas de caja,
truncamiento, etiquetas ausentes y advertencias de integridad. El analizador
no escribe dentro de `Dataset Original/`.

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" `
  --background `
  --python scripts\generate_annotation_dataset.py `
  -- --seed 0 `
     --image-count 100 `
     --captures-per-scene 1 `
     --reference-profile outputs/domain_analysis/real_vs_synthetic/domain_comparison.json
```

La salida predeterminada se escribe en:

```text
outputs/datasets/uchuva_real_matched_pilot_seed_0/
  data.yaml
  labels.txt
  generation_config.json
  dataset_report.json
  manifest.jsonl
  rejected_scenes.jsonl
  images/{train,val,test}/
  labels/{train,val,test}/
  previews/{train,val,test}/
  qa_cycles/{train,val,test}/
```

El reparto 80/10/10 se hace por escena completa; una geometria no aparece en
mas de un split. El calendario reproducible aproxima la referencia real con
59 % de encuadres verticales, 89/10/1 % de imagenes con 1--5, 6--10 y mas de
10 capachos, mezcla de primeros planos/contexto y 10 % de encuadres de borde.
Las cajas se derivan de la mascara exacta de instancia antes del posprocesado
JPEG y se aceptan con al menos 24 pixeles visibles y 6 x 6 pixeles de extension.

La captura RGB mezcla exposicion, balance de blancos, profundidad de campo,
filtrado, dithering y compresion JPEG. Los ambientes procedurales incluyen
follaje cercano, suelo con gramineas/material seco y fondos aislados; nunca se
reutilizan pixeles del dataset real.

Para una comprobacion rapida puede reducirse `--image-count` y
`--cycles-qa-count`. `--resume` conserva solo escenas cuyas imagenes, TXT y previews
coinciden con los hashes del manifiesto. `--keep-masks` conserva las mascaras
reproductivas intermedias que normalmente se eliminan.

Esta iteracion no instala PyTorch, Ultralytics ni dependencias de ML. El
benchmark real/sintetico/mixto queda como fase posterior sujeta a aprobacion.

### Resultado reproducible `seed=0`

El piloto generado en `outputs/datasets/uchuva_real_matched_pilot_seed_0/`
contiene 100 escenas independientes, 383 cajas de clase `0`, splits 80/10/10,
100 previews y 12 controles Cycles. No se observaron colisiones fisicas,
capachos abiertos ni frutos renderizables.

La comparacion final queda en
`outputs/domain_analysis/real_vs_real_matched_pilot/`. Las tasas sinteticas
efectivas fueron 59 % vertical, 89/10/1 % por bandas de objetos,
28.72/54.31/16.97 % por bandas de area y 6.79 % de cajas de borde. La brecha
media de composicion bajo a 1.27 puntos porcentuales. La luminancia mediana
subio de 88.55 en el piloto anterior a 103.83; la referencia real es 124.71.

Limitaciones visuales conocidas: la vegetacion de contexto sigue siendo
low-poly, la pubescencia se aproxima con respuesta de material y no con pelos
geometricos, la venacion secundaria es procedural y las hojas/capachos aun
requieren calibracion con mediciones locales. Estas cifras indican convergencia
de distribuciones, no equivalencia fotografica ni utilidad ML demostrada.

## Texturas vasculares sintéticas

La biblioteca activa está en `Assets/textures/uchuva_v2/`; v1 se conserva para
comparación. V2 contiene dos hojas, cuatro capachos verdes, tres pajizos y tres
secos. Las variantes verdes incluyen contraste vascular y oscurecimiento
próximo al pedúnculo, asignados por órgano y registrados en el JSON.

```powershell
python scripts/generate_texture_assets.py --seed 1701 --resolution 512
```

Blender carga automáticamente los mapas mediante `leaf_uv` y `calyx_uv`. Las
hojas usan una superficie casi plana, albedo más oscuro y rugosidad 0.78--0.90;
no se superpone el patrón diagonal procedural anterior. Los estados de evidencia
y hashes se conservan en `manifest.json`.

El terreno de las escenas anotables y el plano de referencia usan ahora una
extensión efectiva mínima de 260 unidades. Sus bordes quedan más allá del plano
lejano de las cámaras (`clip_end=120`) y no pueden aparecer como el corte
cuadrado del parche; el material conserva su densidad de textura aunque cambie
la extensión.

El `.blend` portable contiene ademas el Text Block
`RUN_UCHUVA_DATASET_PILOT.py`. Sus constantes iniciales controlan semilla,
resolucion, numero de imagenes, muestras Cycles y directorio de salida. Al
ejecutarlo desde el Text Editor usa el codigo y los assets CC0 empaquetados en
el propio archivo.

## Grafo de contexto para agentes

El archivo `docs/repository_context_graph.json` es un mapa arquitectonico
pequeno y respaldado por evidencia. Complementa `AGENTS.md` con nodos para
subsistemas, puntos de entrada, artefactos, pruebas, restricciones y decisiones,
ademas de relaciones explicitas entre ellos. `AGENTS.md` conserva la autoridad
prescriptiva; el grafo solo describe como esta organizado el proyecto.

La adopcion se inspira en el *Repository Intelligence Graph* (RIG), cuyo
estudio serializa un mapa de repositorio como JSON, y en la practica reciente
de grafos de conocimiento basados en archivos. El formato de este proyecto es
local y no pretende ser un estandar ni reproducir automaticamente las mejoras
del estudio:

- <https://arxiv.org/abs/2601.10112>
- <https://2context.dev/>

No se instalaron 2context, Graphiti, una base de grafos ni dependencias nuevas.
El `.git` local no contiene historial util para una extraccion basada en
commits. La evidencia usa rutas relativas y simbolos o encabezados estables;
los numeros de linea y los archivos bajo `outputs/` no son fuentes de verdad.

Validacion legible:

```powershell
python scripts\validate_repository_context_graph.py
```

Reporte para automatizacion:

```powershell
python scripts\validate_repository_context_graph.py --json
```

El grafo debe actualizarse cuando cambien limites entre modulos, la cadena
morfologia--Blender--anotaciones, artefactos primarios o restricciones
cientificas. Una refactorizacion interna que conserve esas relaciones no exige
editarlo. Para tareas triviales y locales no es necesario cargarlo completo.

## Piloto denso estricto v3

El perfil predeterminado de nuevos pilotos es `dense_staked_crop`: genera 20
árboles morfológicos completos en dos filas escalonadas y un tutor rectangular
de madera por planta. El dosel geométrico simplificado quedó desactivado; el
entorno conserva suelo, residuos y vegetación baja.

La adaptación ejecuta tres iteraciones de cultivo y ocho iteraciones de
resolución global 3D antes de Blender. Usa cápsulas para ejes y pecíolos,
prismas delgados para hojas, elipsoides para capachos y cajas orientadas para
tutores. Blender sólo interpreta la pose resultante y realiza una auditoría
final BVH sobre las mallas evaluadas. Una escena con interpenetraciones no
exceptuadas no puede declararse válida. La oclusión 2D permanece permitida y
el contrato YOLO continúa siendo una sola clase: `0 = calyx`.
