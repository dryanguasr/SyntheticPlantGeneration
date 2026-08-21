# SyntheticPlantGeneration

Plataforma experimental para estudiar aumentación de datos, generación
procedural de *Physalis peruviana* y su uso en robótica agrícola. El repositorio
se organiza en tres frentes interoperables:

1. aumentación clásica y sus baselines experimentales;
2. generación sintética morphology-first para Blender y visión artificial;
3. una interfaz morphology-first hacia Gazebo para percepción e interacción
   robot-planta.

El núcleo botánico vigente permanece en `src/uchuva_lsystem/`. Blender y Gazebo
se tratan como intérpretes distintos de una morfología serializable, no como
fuentes alternativas de la arquitectura de la planta.

```text
                           ┌─→ Blender → imágenes / anotaciones / ML
morfología serializable ───┤
                           └─→ Gazebo  → percepción / interacción / robot
```

## Frentes interoperables

| Frente | Ruta principal | Estado |
|---|---|---|
| Aumentación clásica | `src/uchuva_classical_augmentation/` | E0/E1/E2 históricos preservados; campaña v2 reproducible en desarrollo |
| Generación sintética | `src/uchuva_lsystem/` | Implementación vigente y madura |
| Gazebo | `src/uchuva_gazebo/` | Interfaz semántica por LOD; aún no emite SDF |
| Contribuciones externas | `contributions/` | Snapshots atribuidos, separados del código vigente |

La implementación vigente del generador sigue este contrato:

```text
parámetros con procedencia
  → morfología serializable
  → crecimiento multi-planta sincronizado
  → validación y política de contacto
  → geometría Blender
  → anotaciones
```

## Estado vigente

| Componente | Versión o ruta actual |
|---|---|
| Modelo estructural | Variante `E_plus_contact_policy_clearance` |
| Preset morfológico | `trained_trellis` |
| Escena de cultivo | `dense_trellis_synchronous` |
| Competencia de copa | Estratos bajo/medio/alto con campo de luz proyectado |
| Render predeterminado | `standard_eevee` |
| Texturas | `assets/textures/current/` |
| Fenología de dataset v2 | `literature_cohort_v1` |
| Fondo de dataset v2 | `layered_understory_v2` |
| Código del generador | `src/uchuva_lsystem/` |
| Baseline clásico | `src/uchuva_classical_augmentation/protocol.py` |
| Aumentación clásica reproducible | `src/uchuva_classical_augmentation/v2/` |
| Interfaz Gazebo | `src/uchuva_gazebo/` |
| Entradas ejecutables | `scripts/` |
| Escena para revisión | `outputs/current_review/` |
| Blend de fidelidad vigente | `outputs/current_review/uchuva_fidelity_competition_seed_025.blend` |
| Dataset sintético original | `outputs/datasets/uchuva_original_synthetic_seed_1000_v1/` |
| Checkpoint híbrido ganador | `outputs/experiments/checkpoint_interpolation_scale80_seed_1000_v1/interpolated_checkpoints/natural_hybrid_alpha_045.pt` |
| Resultado híbrido preliminar | 0.690637 mAP50–95 frente a 0.682706 natural |
| Reporte del experimento | `docs/reports/resultado_dataset_hibrido_2026-08-01.md` |
| Validación humana | `outputs/human_validation/` |
| Prototipos anteriores | `legacy/` |
| Resultados históricos | `outputs/archive/` |

El código bajo `src/uchuva_lsystem/` es la única implementación vigente del
modelo morfológico. Los archivos bajo `legacy/` se conservan como evidencia
histórica y no deben usarse para definir arquitectura botánica.

## Navegación

```text
SyntheticPlantGeneration/
├── src/
│   ├── uchuva_lsystem/                 modelo procedural y pipeline vigentes
│   ├── uchuva_classical_augmentation/  contrato histórico + pipeline v2 reproducible
│   └── uchuva_gazebo/                  interfaz semántica morphology → Gazebo
├── contributions/                      entregas externas preservadas y atribuidas
├── scripts/                            comandos ejecutables
├── tests/                              regresiones Python puras
├── docs/
│   ├── architecture/                   arquitectura y contratos del modelo
│   ├── governance/                     procedencia, incertidumbre y decisiones
│   ├── guides/                         protocolos y guías operativas
│   ├── reports/                        reportes fechados de experimentos
│   ├── references/                     bibliografía y rutas públicas, sin PDFs
│   ├── workstreams/                    definición de los tres frentes
│   └── drafts/                         borradores locales; fuera de Git
├── assets/
│   └── textures/
│       ├── current/                    biblioteca activa
│       └── legacy/                     generaciones previas
├── outputs/                             artefactos generados; no versionados
├── legacy/                              prototipos reemplazados
└── Dataset Original/                    fuente real local de solo lectura
```

Índices detallados:

- [Documentación](docs/README.md)
- [Scripts actuales](scripts/README.md)
- [Activos](assets/README.md)
- [Resultados](outputs/README.md)
- [Contribuciones](contributions/README.md)
- [Legado](legacy/README.md)

## Documentación y referencias

La documentación producida por el proyecto se versiona bajo `docs/`. Solo
`docs/drafts/` permanece fuera del control de versiones.

Los artículos científicos de referencia no se almacenan como copias PDF en el
repositorio. Las referencias utilizadas por el proyecto son de acceso libre o
cuentan con una versión pública disponible en sus ubicaciones de origen,
repositorios institucionales o servicios públicos de preprints. Sus DOI, URL y
metadatos se conservan en `docs/references/` para poder localizarlos desde la
fuente pública correspondiente.

## Generar la escena Blender vigente

Blender 5.1:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background `
  --python scripts\generate_blender_cultivation_scene.py -- `
  --seed 1 `
  --plant-count 20 `
  --model-variant E_plus_contact_policy_clearance `
  --audit-mode proxy `
  --preview-output outputs\current_review\uchuva_multiplant_variant_e_contact_clearance_seed_001_preview.png
```

El modo `proxy` permite producir rápidamente un `.blend` de revisión con la
auditoría morfológica estricta registrada. Para aceptación final de geometría
use `--audit-mode full_mesh`.

## Comandos principales

Python puro:

```powershell
$env:PYTHONPATH='C:\dev\SyntheticPlantGeneration\src'
python scripts\generate_morphology_tree.py --seed 1
python scripts\generate_morphology_diagnostics.py --seed-start 0 --seed-count 10
python scripts\run_model_variant_ablation.py --help
python scripts\build_dataset_reference_manifest.py
python scripts\prepare_hybrid_experiments.py --help
python scripts\run_hybrid_training.py --help
python scripts\run_curriculum_training.py --help
python scripts\calibrate_synthetic_scale.py --help
python scripts\run_checkpoint_interpolation.py --help
python scripts\calibrate_composition_schedule.py --help
python scripts\audit_literature_cohort_morphologies.py --help
python scripts\analyze_detection_errors.py --help
python scripts\audit_virtual_fidelity_pilot.py --help
```

Dataset real-matched en EEVEE normal:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background `
  --python scripts\generate_annotation_dataset.py -- `
  --seed 1000 --image-count 100 --cycles-qa-count 0 `
  --reference-profile outputs\domain_analysis\real_vs_fidelity_pilot\domain_comparison.json `
  --output-dir outputs\datasets\uchuva_original_synthetic_seed_1000_v1
```

La calibración v2 usa únicamente `train` real. `val` queda para selección
experimental y `test` no participa en el perfil de composición, en la
selección morfológica ni en la preparación de mezclas; queda reservado para la
comparación final de modelos.

Diagnósticos Blender:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background `
  --python scripts\render_structural_diagnostics.py -- `
  --seed 1 --model-variant E_plus_contact_policy_clearance
```

Validación humana de un cambio significativo:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background `
  --python scripts\generate_human_validation_suite.py -- `
  --change-id standard_render_protocol_v1 `
  --change-category render `
  --bootstrap
```

El comando genera diez casos EEVEE estándar y requiere auditoría de malla.
Cycles solo se usa si se selecciona explícitamente un perfil Cycles. Para
verificar la integración sin crear evidencia use `--smoke --case-id case_07`.
El protocolo completo está en
`docs/guides/protocolo_validacion_humana.md`.

## Verificación

```powershell
$env:PYTHONPATH='C:\dev\SyntheticPlantGeneration\src'
python -m unittest discover -s tests -v
python scripts\validate_repository_context_graph.py
```

Las pruebas puras no requieren Blender. La auditoría de malla evaluada sí se
ejecuta dentro de Blender.

## Contratos que deben preservarse

- hojas, ramas y unidades reproductivas nacen de nodos o axilas;
- el fruto permanece oculto dentro del capacho cerrado;
- el contrato YOLO continúa siendo `{"calyx": 0}`;
- se distinguen colisión física, ocupación blanda, oclusión visual y contacto
  intencional;
- cada ejecución registra semilla, preset, variante y procedencia;
- `Dataset Original/` es de solo lectura;
- validación y prueba de las matrices híbridas contienen solo imágenes reales;
- el entrenamiento híbrido fija modelo inicial, semilla, resolución, épocas y
  test natural; cada corrida puede reanudarse desde `last.pt`;
- no se añaden dependencias externas para el pipeline base.

## Licencia

El código fuente original desarrollado para este repositorio se distribuye bajo
la [licencia MIT](LICENSE), salvo indicación explícita en contrario.

La licencia MIT del repositorio **no relicencia automáticamente**:

- entregas estudiantiles o de terceros preservadas bajo `contributions/`;
- datasets;
- pesos de modelos;
- artículos científicos u otro material de terceros.

Cada uno de esos elementos conserva su autoría y sus términos propios. Consulte
`contributions/README.md` y `docs/references/README.md` para el alcance de esas
exclusiones.
