# Arquitectura morfológica multi-planta sincronizada

## Resultado de esta iteración

La ruta principal conserva el contrato:

```text
parámetros con procedencia
  → morfologías potenciales por semilla
  → propuestas de crecimiento sincronizadas
  → política de contacto y ocupación compartida
  → morfologías aceptadas y serializables
  → validación
  → geometría Blender
  → auditoría BVH/clearance
  → anotaciones
```

`adapt_cultivation_morphologies()` permanece disponible como
`legacy_posthoc`. La API nueva es:

```python
generate_cultivation_morphologies(
    scene,
    params,
    model_variant="E_plus_contact_policy_clearance",
)
```

El modo nuevo no aplica una relajación global silenciosa al final. Las
desviaciones y reducciones de longitud se deciden antes de incorporar un eje
y quedan registradas como `ProposalDecision`.

## Separación de responsabilidades

| Módulo | Responsabilidad |
|---|---|
| `morphology.py` | Dataclasses botánicas, esquema aditivo y round trip JSON |
| `parameters.py` | Presets, presupuestos, vigor, taper y ruido correlacionado |
| `grammar.py` | Morfología potencial nodal de cada individuo |
| `support.py` | Postes, líneas, amarres, zonas y contactos del trellis |
| `spatial.py` | Índice espacial y política por par de órganos |
| `growth.py` | Propuestas, prioridad canónica y decisiones sincronizadas |
| `light_competition.py` | Campo diario proyectado y competencia por estratos |
| `cultivation.py` | API A–F y compatibilidad con el modo legado |
| `collisions.py` | Proxies finales y taxonomía de contacto |
| `blender_geometry.py` | Interpretación geométrica y auditoría de malla |
| `metrics.py` | Métricas 3D, proyectivas proxy, rendimiento y huella fuente |

Ninguno de los módulos puros importa `bpy`.

## Desarrollo individual

Los presets disponibles son:

- `initial_migration_manual_guess`: reproduce el modelo recursivo legado;
- `natural_unpruned`: mayor liberación lateral y orden máximo 3;
- `trained_trellis`: crecimiento presupuestado y entrenamiento contra soporte;
- `compact_research_reference`: arquitectura de menor extensión.

En los tres presets nuevos cada eje registra:

- presupuesto de longitud y remanente;
- máximo de entrenudos;
- vigor y decaimiento por orden;
- paso de desarrollo;
- fase de ruido correlacionado;
- eventos de consumo del presupuesto;
- contactos de soporte.

Las hojas conservan una lámina simple y casi plana. Su escala depende de orden
y vigor. En `trained_trellis` la densidad aumenta mediante estructura nodal
válida y no mediante hojas sueltas. La postura se elige entre candidatos
deterministas alrededor de la orientación preferida, ocupa claros del campo de
luz bajo/medio/alto y registra la rotación, la cobertura y sus costes.

## Soporte previo al crecimiento

`dense_trellis_synchronous` crea un `SupportSystem` antes de generar las
decisiones morfológicas:

- dos postes extremos por hilera;
- tres líneas longitudinales;
- dos o tres amarres por planta;
- zonas de guía;
- contactos intencionales explícitos.

El soporte no se desplaza después para buscar un corredor libre. La ablación
`support_enabled=False` usa la misma semilla y produce decisiones diferentes,
lo que está cubierto por prueba automática.

## Ciclo sincronizado

En cada paso:

1. se calculan marcos nodales de todas las plantas activas;
2. se recopilan los ejes potenciales cuyo padre ya existe;
3. se ordenan por `(order, -vigor, plant_id, axis_id)`;
4. se evalúan desviaciones y fracciones de longitud deterministas;
5. se consulta ocupación, soporte, gravedad, deformación y ruido;
6. se aplica `accepted`, `deviated`, `shortened`, `deferred` o `cancelled`;
7. se actualiza el índice antes de resolver la propuesta siguiente.

Con el preset tutorado, la evaluación también distingue `stratum_expansion` y
`apical_lift_to_trellis`. Después de resolver los ejes, las hojas de todos los
individuos se intercalan por estrato y paso de desarrollo contra un campo de
luz compartido con cinco muestras diurnas.

Permutar la lista de plantas no cambia topología ni decisiones. La prueba usa
árboles serializados completos y el registro ordenado de decisiones.

El deslizamiento tangencial amplía candidatos para ramas finas y puede
desactivarse. La colonización espacial está detrás de
`space_colonization_enabled=False`; es una heurística opcional inspirada en
árboles y no evidencia biológica de uchuva.

## Política de contacto

La política distingue:

- `hard_occupancy`: tallo–tallo, tallo–capacho, capacho–capacho y soporte rígido;
- `soft_occupancy`: hojas frente a tallos, capachos o postes;
- `visual_occlusion`: solapamiento proyectivo entre hojas;
- `intentional_support`: tallo con línea o amarre;
- `near_contact`: proximidad informativa sin violación.

Los umbrales iniciales son `engineering_heuristic` y se auditan por par. Los
reportes no usan “cero conflictos” como sinónimo de clearance suficiente:

```text
proxy_conflicts
mesh_intersections
clearance_violations
intentional_contacts
near_contacts
visual_occlusions
```

Blender evalúa mallas transformadas a coordenadas mundiales. El reporte
incluye objetos, IDs semánticos, pares de triángulos para intersecciones y una
estimación de clearance de superficie. La hoja usa espesor virtual explícito.

## Variantes A–F

| Variante | Contenido |
|---|---|
| A | Baseline independiente + corrección posterior legado |
| B | Morfología individual presupuestada |
| C | B + soporte estructural previo |
| D | C + coordinación multi-planta |
| E | D + matriz de contacto, clearance y deslizamiento tangencial |
| F | E + colonización espacial opcional |

F permanece desactivada por defecto. Solo debe conservarse si mejora la copa
sin empeorar la razón longitud/hijas y sin superar 2× el tiempo de E.

## Reproducción

Python puro:

```powershell
$env:PYTHONPATH='C:\dev\SyntheticPlantGeneration\src'
python scripts\generate_morphology_diagnostics.py --seed-start 0 --seed-count 30 --model-variant E_plus_contact_policy_clearance
```

Manifest real, sin escribir en `Dataset Original/`:

```powershell
python scripts\build_dataset_reference_manifest.py
```

Siete renders de diagnóstico en Blender:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background `
  --python scripts\render_structural_diagnostics.py -- `
  --seed 1 --model-variant E_plus_contact_policy_clearance
```

Los modos son `skeleton`, `branch_order`, `plant_id`,
`leaf_scale_correction`, `contacts`, `global` y `close`. Cámara, luz y
materiales base se fijan por semilla para comparar variantes.

## Calibración y evaluación

`scripts/build_dataset_reference_manifest.py` clasifica todas las etiquetas de
`train` y `val` por número de objetos y área mediana de caja:

- `train`: calibración;
- `val`: evaluación de esta iteración;
- `test`: excluido e intacto.

El manifest contiene únicamente medidas derivadas y hashes de etiquetas fuera
del dataset original. Las métricas proyectivas puras son proxies ortográficos;
las medidas de cámara Blender son la autoridad para la comparación final.

## Evidencia y límites

La separación estructura/proceso sigue el enfoque de modelos funcionales-
estructurales descrito por Vos et al. El crecimiento sensible al entorno se
usa metodológicamente según Měch y Prusinkiewicz. La colonización espacial
opcional sigue a Runions et al. Ninguno de esos algoritmos se atribuye como
mecanismo específico de *Physalis peruviana*.

La coexistencia de estados fenológicos se conserva por la escala BBCH de la
especie descrita por Ramírez et al. Los valores dimensionales siguen sujetos
al registro de procedencia en `docs/governance/registro_evidencia.md`.

Referencias:

- Vos et al. (2010), *Functional–structural plant modelling*.
- Měch y Prusinkiewicz (1996), *Visual Models of Plants Interacting with
  Their Environment*.
- Runions et al. (2007), *Modeling Trees with a Space Colonization
  Algorithm*.
- Ramírez et al. (2013), escala BBCH de *Physalis peruviana*.
