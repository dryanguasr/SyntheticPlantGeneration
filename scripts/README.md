# Comandos vigentes

Todos los scripts de esta carpeta son entradas actuales. Los scripts
reemplazados están en `legacy/scripts/`.

## Morfología y calibración

| Script | Propósito |
|---|---|
| `generate_morphology_tree.py` | Exporta un árbol y su validación sin Blender |
| `generate_morphology_diagnostics.py` | Produce métricas JSON, CSV y Markdown |
| `run_model_variant_ablation.py` | Ejecuta la matriz de variantes A–F |
| `build_dataset_reference_manifest.py` | Deriva el manifest train/val sin tocar test |
| `compare_real_vs_synthetic_domain.py` | Compara dominio real y sintético |
| `calibrate_composition_schedule.py` | Calibra la mezcla de cámaras exclusivamente contra `train` real |
| `audit_literature_cohort_morphologies.py` | Audita cohortes y contrato crítico sin Blender |
| `analyze_detection_errors.py` | Diagnostica TP/FP/FN y localización solo sobre `val` real |
| `audit_virtual_fidelity_pilot.py` | Aplica los criterios de aceptación y bloqueo del piloto v2 |
| `create_dataset_sample_sheet.py` | Genera una lámina determinista de revisión visual |
| `calibrate_synthetic_scale.py` | Deriva un dataset con escala aparente ajustada usando solo train/val reales |
| `prepare_hybrid_experiments.py` | Prepara baseline y mezclas real/sintético con val/test reales |
| `run_hybrid_training.py` | Entrena la matriz con un protocolo común y compara mAP50-95 en test natural |
| `run_hybrid_fidelity_study.py` | Audita y repara fugas, ejecuta el estudio multisemilla por val real y sella el test hasta bloquear un ganador |
| `run_curriculum_training.py` | Preentrena con sintético y afina luego con el natural completo |
| `run_natural_refinement.py` | Cierra un entrenamiento mixto con un tramo corto exclusivamente natural |
| `run_checkpoint_interpolation.py` | Selecciona por validación una interpolación de pesos natural–híbrida |

## Blender

| Script | Propósito |
|---|---|
| `generate_blender_cultivation_scene.py` | Genera la escena multi-planta vigente |
| `generate_blender_single_plant_preview.py` | Preview detallado de una planta |
| `render_structural_diagnostics.py` | Siete vistas estructurales comparables |
| `generate_annotation_pilot.py` | Piloto RGB/anotable |
| `generate_annotation_dataset.py` | Dataset YOLO por escenas |
| `generate_virtual_fidelity_pairs.py` | Comparaciones v1/v2 con condiciones pareadas |
| `generate_human_validation_suite.py` | Diez casos antes/después con EEVEE estándar y Cycles opcional |
| `example_run_blender_background.ps1` | Ejemplo Windows |

## Puente hacia Gazebo

| Script | Propósito |
|---|---|
| `export_gazebo_plant.py` | Exporta un plan JSON puro por LOD desde una morfología; no produce SDF ni requiere Gazebo |

La entrega estudiantil de aumentación clásica se conserva bajo
`contributions/diego_amaya/`. No se registra como entrada vigente del
generador: su lanzador mantiene su propio protocolo y las recetas E1/E2 aún
deben recuperarse o reimplementarse antes de que esa línea pueda producir
datasets nuevos de manera reproducible.

## Classical Augmentation v2

| Script | Propósito |
|---|---|
| `analyze_real_training_domain.py` | Sella splits y mide geometría/fotometría usando sólo train |
| `build_classical_augmentation_v2.py` | Construye recetas trazables; genera 25 muestras smoke por defecto |
| `audit_classical_augmentation_v2.py` | Verifica imágenes, labels, hashes, procedencia, splits y distribución de tamaños |
| `preview_classical_augmentation_v2.py` | Genera láminas original/aumentada/overlay de cajas |
| `run_classical_augmentation_v2_screening.py` | Ejecuta smoke training o screening de 3 semillas sin augmentación online |
| `run_classical_augmentation_v2_campaign.py` | Ejecuta la confirmación congelada de escenarios seleccionados |
| `summarize_classical_augmentation_v2.py` | Agrega mAP y calcula Recall sujeto a Precision ≥ 0,98 sobre val |
| `lock_classical_augmentation_v2_selection.py` | Sella decisión, recetas, datasets, checkpoints y umbrales de val antes del test final |

La configuración serializable vive en
`configs/classical_augmentation_v2/campaign_v1.json`. El test permanece fuera
de cualquier selección y sólo puede consultarse después de congelar la campaña.

## Activos y mantenimiento

| Script | Propósito |
|---|---|
| `generate_uchuva_texture_library.py` | Regenera `assets/textures/current/` |
| `download_cc0_assets.py` | Descarga y verifica activos CC0 del entorno |
| `promote_human_validation_suite.py` | Promueve una suite revisada sin sobrescribirla |

Los nombres incluyen el artefacto producido; no se usan números de versión en
scripts vigentes. La versión experimental se registra en la configuración y
en los artefactos, no en el nombre del programa.
