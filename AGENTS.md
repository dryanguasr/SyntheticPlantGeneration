# AGENTS.md

This file gives repository-specific instructions to Codex and other coding agents.

## Project identity

This repository integrates three related research workstreams for agricultural robotics:

1. conventional / classical image augmentation baselines;
2. a procedural **cape gooseberry / uchuva** (*Physalis peruviana*) generator;
3. a morphology-first bridge toward Gazebo for robot-plant simulation.

The botanical source of truth is the morphology-first functional-structural
model under `src/uchuva_lsystem/`. Blender and Gazebo are downstream
interpreters and must not redefine botanical architecture.

The current conceptual direction is:

```text
morphological tree → validated plant structure ─┬→ Blender geometry → annotations
                                                 └→ Gazebo export plan → robot simulation
```

## Non-negotiable direction

Do **not** continue refining the generic aesthetic prototype as if it were the target model.

The file `legacy/prototypes/generic_blender_plant_v0_5.py` (formerly
`planta_procedural_v05.py`) is a **legacy geometric prototype**. It may be
reused for utilities, but it must not define the botanical architecture.

Reusable ideas from v0.5:

- Blender scene cleanup;
- material creation;
- cylinder-between-points helper;
- simple leaf mesh generation;
- simple fruit/calyx geometry;
- camera/light setup;
- JSON export.

Do not use v0.5 as the main biological model.

## Target architecture

Create or maintain this conceptual separation:

```text
src/uchuva_lsystem/                  # morphology-first plant model and Blender pipeline
src/uchuva_classical_augmentation/   # conventional augmentation contracts / baselines
src/uchuva_gazebo/                   # pure morphology-facing Gazebo hand-off
contributions/                       # attributed external/student snapshots
docs/                                # versioned project-authored documentation
```

Within `src/uchuva_lsystem/`, preserve the separation between pure morphology
and Blender interpretation:

```text
src/uchuva_lsystem/morphology.py       # data model / dataclasses
src/uchuva_lsystem/parameters.py       # parameter ranges and presets
src/uchuva_lsystem/grammar.py          # L-System / morphology generation
src/uchuva_lsystem/blender_geometry.py # geometry interpretation
src/uchuva_lsystem/blender_scene.py    # Blender scene, camera, lights, cleanup
src/uchuva_lsystem/exporters.py        # JSON and annotation exports
src/uchuva_lsystem/validation.py       # morphology and geometry validation
```

The first stable deliverable should be a JSON-serializable morphology tree, even before a beautiful render.

## Repository context graph

For architecture, scientific-model, validation, dataset, or workstream tasks,
read `docs/repository_context_graph.json` after this file. It is a versioned,
evidence-backed descriptive map of subsystems, entrypoints, artifacts, tests,
constraints, and decisions. Do not load the full graph for a trivial,
file-local edit.

`AGENTS.md` remains the prescriptive authority and overrides the context graph
if they conflict. The graph must not treat generated outputs, external
contributions, or legacy code as authoritative evidence. After changing module
boundaries, pipelines, scientific constraints, or primary artifacts, run:

```text
python scripts/validate_repository_context_graph.py
```

## Documentation policy

Project-authored architecture, governance, guides, reports, bibliographic
metadata, and workstream documents belong under `docs/` and are versioned.

Do not commit:

- `docs/drafts/`;
- downloaded PDF copies of reference articles;
- local raw reference material.

Reference papers used by the project are publicly available from their original
publishers, DOI landing pages, public repositories, or preprint services. Keep
DOI/URL metadata in `docs/references/` instead of duplicating article files.

## Botanical assumptions to preserve

The model should represent uchuva as a nodal, branching plant with axillary reproductive structures.

Important features:

- main axis and lateral branches;
- internodes and nodes;
- leaves associated with nodes;
- petiole + leaf blade;
- axillary buds;
- solitary axillary flowers/fruits;
- pedicel connecting axil to reproductive unit;
- persistent inflated calyx/capacho;
- fruit inside, partially visible, hidden, or exposed;
- mixed phenological states on the same plant.

Avoid placing fruits or leaves arbitrarily in global coordinates.

## Conceptual grammar

Use this as the starting point:

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

The grammar may be implemented procedurally first; it does not need to be a formal string-rewriting engine in the first version.

## Development style

- Prefer small, incremental changes.
- Keep code readable for engineering students.
- Use clear dataclasses and explicit serialization methods.
- Keep Blender-specific code separate from morphology-generation code.
- Keep Gazebo-specific runtime code separate from the pure export contract.
- Avoid hidden global state except for explicit configuration constants.
- Use reproducible seeds.
- Record script version, seed, and parameter preset in every exported JSON.
- Do not introduce heavy dependencies unless explicitly requested.
- Prefer standard library + Blender Python API for the core generation path.

## Language and naming

The user works primarily in Spanish, but code identifiers should be clear and consistent.

Preferred code identifiers: English.

Preferred user-facing docs: Spanish.

Acceptable domain terms:

- `calyx` for cáliz/capacho;
- `pedicel` for pedicelo;
- `petiole` for pecíolo;
- `internode` for entrenudo;
- `node` for nodo;
- `axillary_bud` for yema axilar;
- `reproductive_unit` for flor/fruto/cáliz.

## Validation rules

Add warnings or validation reports when:

- a fruit is not attached to a node/axil;
- a calyx is missing for a fruit stage that requires it;
- a pedicel does not connect axil and reproductive unit;
- a leaf is not associated with a node;
- branch order is inconsistent;
- branch/axis radius does not decrease with order;
- scale ratios are implausible;
- collision is physically impossible;
- visual occlusion is being confused with geometric intersection.

Validation should distinguish:

```text
geometric collision        # physically invalid
visual occlusion           # potentially useful for synthetic data
out-of-range morphology    # botanically suspicious
```

## Expected initial migration task

If the repository only contains `planta_procedural_v05.py` and related notes:

1. Create the recommended folder structure.
2. Move `planta_procedural_v05.py` to `legacy/`.
3. Create empty but documented modules under `src/uchuva_lsystem/`.
4. Create or update `.gitignore`.
5. Version project-authored documentation and bibliographic metadata; keep drafts, downloaded articles, and local checkpoints outside version control.
6. Do not rewrite the entire generator yet.
7. Do not implement a full L-System before the morphology dataclasses exist.

## Testing and sanity checks

At minimum, future scripts should support:

```text
seed → morphology_tree_seed_X.json
seed → Blender scene
seed → validation_report_seed_X.json
```

For early non-Blender modules, use plain Python scripts or simple unit tests where possible.

Do not require Blender to test pure morphology generation or the pure Gazebo export contract.

## Git and output hygiene

Do not commit generated output by default.

Ignore:

```text
outputs/
generated_specs/
docs/drafts/
docs/references/raw/
docs/references/**/*.pdf
*.blend1
__pycache__/
.venv/
*.pyc
```

Small example JSON files may be committed under `examples/` only if useful for documentation.

## Scientific caution

Do not invent precise botanical or physical parameter values as facts.

If a value is estimated, label it as:

```text
estimated
manual_initial_guess
engineering_heuristic
to_be_measured
literature_reported
```

Prefer explicit uncertainty over false precision.

## Licensing and external contributions

The repository's root MIT license applies to original source code authored for
this repository unless a file states otherwise. It does not automatically
relicense student or third-party snapshots under `contributions/`, datasets,
model weights, or reference articles. Preserve authorship and original terms.

## What to ask before doing

Ask the user before:

- adding external dependencies;
- changing the scientific scope;
- converting the project to a package with build tooling;
- deleting legacy scripts;
- generating large batches of renders;
- changing annotation classes;
- replacing Spanish docs with English docs.
