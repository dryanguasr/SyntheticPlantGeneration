# Prompt de migración para Codex

Recibe esta carpeta como el inicio de un proyecto de generación procedural de uchuva (*Physalis peruviana*) para datos sintéticos en robótica agrícola.

La carpeta ya contiene una versión exploratoria llamada `planta_procedural_v05.py` o equivalente. Esa versión mejoró la geometría en Blender, pero **no debe ser tratada como arquitectura botánica definitiva**. Su rol correcto es `legacy`: sirve como referencia para utilidades de Blender, no como modelo morfológico de uchuva.

## Contexto científico-técnico

El proyecto está migrando desde:

```text
planta procedural genérica con tallo, hojas y frutos
```

hacia:

```text
modelo morfológico-paramétrico de uchuva basado en L-System / FSPM
```

La nueva arquitectura debe partir de una representación jerárquica:

```text
Plant
 └─ Axis / Branch
     ├─ Internode
     ├─ Node
     │   ├─ Leaf
     │   ├─ AxillaryBud
     │   └─ ReproductiveUnit / FruitWithCalyx
     └─ Apex
```

No queremos seguir refinando estética genérica. Queremos preparar el proyecto para que el modelo botánico sea explícito, serializable, validable y luego interpretable en Blender.

## Tarea 1: migración estructural inicial

Haz una primera migración limpia y conservadora.

Crea o ajusta la estructura:

```text
.
├─ README.md
├─ AGENTS.md
├─ .gitignore
│
├─ docs/
│  ├─ checkpoint_blender_uchuva_lsystem_03.md        # si existe, mover aquí
│  ├─ modelo_morfologico_inicial_uchuva.md           # crear stub si no existe
│  ├─ referencias_uchuva_lsystem.bib                 # si existe, mover aquí
│  └─ decisiones_tecnicas.md                         # crear stub
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

Si los archivos ya existen, no los sobrescribas sin revisar.

## Tarea 2: mover el prototipo

Mueve `planta_procedural_v05.py` a:

```text
legacy/planta_procedural_v05.py
```

Si el archivo tiene otro nombre pero claramente es la versión 0.5, muévelo a `legacy/` conservando el nombre original y deja una nota en `docs/decisiones_tecnicas.md`.

No borres el archivo legacy.

## Tarea 3: crear módulos base

Crea módulos con docstrings y esqueletos mínimos, sin implementar todo todavía.

### `morphology.py`

Crear dataclasses iniciales:

- `Plant`
- `Axis`
- `Internode`
- `Node`
- `Leaf`
- `AxillaryBud`
- `Pedicel`
- `Calyx`
- `Fruit`
- `ReproductiveUnit`

Deben ser serializables a JSON, idealmente con métodos simples como:

```python
to_dict()
```

No dependas de Blender en este archivo.

### `parameters.py`

Crear un preset inicial de parámetros, separando valores:

```text
literature_reported
manual_initial_guess
to_be_measured
```

No inventes precisión falsa. Si un rango es tentativo, déjalo marcado como tentativo.

### `grammar.py`

Crear una función preliminar:

```python
generate_morphology_tree(seed: int, params: dict | None = None) -> Plant
```

Puede devolver un árbol mínimo de prueba, pero debe reflejar la idea:

```text
Apex → Internode + Node + Apex
Node → Leaf + AxillaryBud
AxillaryBud → DormantBud | Branch | ReproductiveUnit
```

No implementes una gramática compleja todavía.

### `exporters.py`

Crear función:

```python
export_json(data, output_path)
```

y, si es útil:

```python
export_morphology_tree(plant, output_path)
```

### `validation.py`

Crear función:

```python
validate_morphology_tree(plant) -> dict
```

Debe devolver un reporte, aunque al inicio solo tenga advertencias básicas.

### `blender_geometry.py` y `blender_scene.py`

Crear stubs documentados. Puedes copiar funciones generales desde `legacy/planta_procedural_v05.py`, pero evita hacer un refactor masivo en esta primera tarea.

## Tarea 4: scripts mínimos

Crea `scripts/generate_single_plant.py` para generar un árbol morfológico y exportarlo a JSON, sin exigir Blender todavía si es posible.

Resultado esperado:

```text
outputs/specs/morphology_tree_seed_0.json
```

Crea `scripts/generate_batch.py` como stub para futuro.

Crea `scripts/run_blender_background.ps1` con ejemplo comentado para ejecutar Blender en background en Windows.

## Tarea 5: .gitignore

Agregar o actualizar `.gitignore` para ignorar:

```text
outputs/
generated_specs/
__pycache__/
*.pyc
.venv/
*.blend1
.DS_Store
```

No ignores `docs/`, `src/`, `scripts/`, `legacy/`, `examples/`.

## Restricciones importantes

- No continuar refinando la estética de la planta v0.5.
- No intentar implementar todo el L-System en esta primera migración.
- No generar renders por lotes.
- No agregar dependencias externas sin preguntar.
- No borrar scripts legacy.
- No cambiar el alcance científico del proyecto.
- No convertir el repo en paquete instalable con `pyproject.toml` todavía, salvo que sea estrictamente necesario y esté justificado.

## Criterios de aceptación

Al terminar, debe existir:

1. Estructura de carpetas clara.
2. `README.md` actualizado.
3. `AGENTS.md` con instrucciones del proyecto.
4. `legacy/planta_procedural_v05.py`.
5. Módulos base en `src/uchuva_lsystem/`.
6. Script `scripts/generate_single_plant.py`.
7. Un JSON de ejemplo generado o instrucciones para generarlo.
8. Un resumen final de cambios.
9. Una lista breve de próximos pasos.

## Próximo paso después de esta migración

Después de esta tarea inicial, la siguiente tarea será implementar de verdad `morphology.py`, `parameters.py` y `grammar.py` para generar un primer árbol morfológico de uchuva defendible, antes de volver a crear geometría en Blender.
