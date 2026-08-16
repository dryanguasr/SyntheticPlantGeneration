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

## Activos y mantenimiento

| Script | Propósito |
|---|---|
| `generate_uchuva_texture_library.py` | Regenera `assets/textures/current/` |
| `download_cc0_assets.py` | Descarga y verifica activos CC0 del entorno |
| `validate_repository_context_graph.py` | Valida arquitectura y evidencia |
| `promote_human_validation_suite.py` | Promueve una suite revisada sin sobrescribirla |

Los nombres incluyen el artefacto producido; no se usan números de versión en
scripts vigentes. La versión experimental se registra en la configuración y
en los artefactos, no en el nombre del programa.
