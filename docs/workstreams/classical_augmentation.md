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

Ejecución experimental, una fase a la vez:

```powershell
# Screening completo: 9 escenarios x 3 semillas x 30 épocas.
python scripts/run_classical_augmentation_v2_screening.py `
  --dataset-root outputs/classical_augmentation_v2/datasets/full `
  --project outputs/classical_augmentation_v2/runs/screening `
  --phase screening --device 0

# Ranking y métricas operacionales/estratificadas, exclusivamente sobre val.
python scripts/summarize_classical_augmentation_v2.py `
  --project outputs/classical_augmentation_v2/runs/screening `
  --output-dir outputs/classical_augmentation_v2/metrics/screening `
  --device 0

# Confirmación de los controles y hasta tres recetas seleccionadas.
python scripts/run_classical_augmentation_v2_campaign.py `
  --dataset-root outputs/classical_augmentation_v2/datasets/full `
  --project outputs/classical_augmentation_v2/runs/confirmatory `
  --scenarios V2-E0 V2-E0R <recetas-seleccionadas> `
  --seeds 1-5 --epochs 50 --device 0

python scripts/summarize_classical_augmentation_v2.py `
  --project outputs/classical_augmentation_v2/runs/confirmatory `
  --output-dir outputs/classical_augmentation_v2/metrics/confirmatory `
  --phase confirmatory `
  --expected-scenarios V2-E0,V2-E0R,<recetas-seleccionadas> `
  --expected-seeds 1,2,3,4,5 --expected-epochs 50 --device 0

# Tras una extensión selectiva a semillas 6-10, repetir el resumen anterior
# añadiendo --allow-adaptive-extension; las recetas no promovidas permanecen en 5 semillas.

# Este comando rehúsa sellar una cohorte de cinco semillas que deba extenderse.
python scripts/lock_classical_augmentation_v2_selection.py `
  --confirmatory-summary outputs/classical_augmentation_v2/metrics/confirmatory/confirmatory_summary.json `
  --project outputs/classical_augmentation_v2/runs/confirmatory

# Único punto de entrada autorizado a test; exige un lock íntegro.
python scripts/run_classical_augmentation_v2_final_test.py --device 0
```

El test no interviene en perfiles, recetas, ranking, checkpoints ni umbrales.
El evaluador final vuelve a verificar hashes del split, aplica los umbrales
escogidos en `val` y registra cada acceso. El test ya fue consultado en trabajo
histórico, por lo que se mantiene congelado pero no se describe como virgen.

### Cierre confirmatorio 2026-08-28

El screening reproducible y su selección de finalistas están documentados en
[`docs/reports/aumento_clasico_v2_screening_2026-08-25.md`](../reports/aumento_clasico_v2_screening_2026-08-25.md).

La confirmación terminó con 40 corridas válidas. V2-E7 se extendió de forma
adaptativa a 10 semillas junto con V2-E0 y V2-E0R; V2-E3 y V2-E6 permanecieron
en cinco. Ninguna receta satisfizo el criterio predeclarado de candidato fuerte.
El lock se selló sin candidatos y el evaluador final cerró sin consultar
`test`. El resultado, las métricas operacionales y el diagnóstico de tiempos se
documentan en
[`docs/reports/aumento_clasico_v2_confirmatory_2026-08-28.md`](../reports/aumento_clasico_v2_confirmatory_2026-08-28.md).

Los datasets, manifiestos extensos, previews, checkpoints y métricas se guardan
en `outputs/classical_augmentation_v2/` y no se versionan. Los reportes
científicos resumidos se conservan bajo `docs/reports/`.
