# Frente A: aumentacion clasica

Este frente contiene transformaciones convencionales de imagen y su evaluacion
como baseline frente a datos reales y sinteticos. No depende de Blender ni de
la morfologia procedural.

Estado actual:

- La entrega de Diego Amaya preservada en `contributions/diego_amaya/` aporta
  un lanzador multisemilla y configuraciones para E0, E1 y E2.
- E1 y E2 existen como datasets precomputados; sus recetas de transformacion
  no estan presentes en el codigo entregado.
- `src/uchuva_classical_augmentation/` registra esa limitacion para impedir
  que el repositorio atribuya reproducibilidad a operaciones no documentadas.
- `src/uchuva_classical_augmentation/v2/` implementa una campaña nueva,
  separada y trazable. No reinterpreta las recetas históricas E1/E2.
- El perfil real v2 usa exclusivamente estadísticas de train y sella los tres
  splits con manifiestos y hashes. Val y test nunca son fuentes de aumentación.

Cuando se recupere o implemente una receta, debe registrar semilla, padres de
cada muestra, parametros, version y hashes. Una derivacion de una foto real
no puede cruzar de `train` a `val` o `test`.

## Classical Augmentation v2

La configuración versionada vive en
`configs/classical_augmentation_v2/campaign_v1.json`. El pipeline separa:

```text
perfil train-only → build de recetas → auditoría → smoke training
  → screening multisemilla → confirmación → test final congelado
```

Comandos principales:

```powershell
python scripts/analyze_real_training_domain.py
python scripts/build_classical_augmentation_v2.py --derived-count 25
python scripts/audit_classical_augmentation_v2.py --dataset-dir <dataset>
python scripts/preview_classical_augmentation_v2.py --dataset-dir <dataset>
```

Los datasets, manifiestos extensos, previews, checkpoints y métricas se guardan
en `outputs/classical_augmentation_v2/` y no se versionan. Los reportes
científicos resumidos se conservan bajo `docs/reports/`.
