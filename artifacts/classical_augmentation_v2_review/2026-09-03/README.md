# Paquete de revisión — Classical Augmentation v2

Preparado el 2026-09-03 para Diego y Laura, por solicitud explícita del titular
del repositorio. Es una instantánea de evidencia experimental, no una nueva
campaña ni una redefinición del protocolo. Los originales en `outputs/` no se
modificaron. No se entrenó ningún modelo ni se evaluó test para este export.

## Por dónde empezar

1. [Informe confirmatorio](snapshot/docs/reports/aumento_clasico_v2_confirmatory_2026-08-28.md).
2. [Informe de screening](snapshot/docs/reports/aumento_clasico_v2_screening_2026-08-25.md).
3. [Recetas y parámetros](snapshot/configs/classical_augmentation_v2/campaign_v1.json).
4. [Guía del protocolo](snapshot/docs/workstreams/classical_augmentation.md).
5. [Decisión de selección extraída](extracted/selected_scenarios.json).
6. [Catálogo de corridas](extracted/run_catalog.json), antes de agregar CSV por cuenta propia.

El resultado de la campaña fue **ninguna receta promovida**. E6/E7 mejoraron
mAP50-95 frente al control remuestreado E0R, pero incumplieron el criterio
operacional por dificultad. La selección y todos los umbrales se obtuvieron
en `val`. El cierre final registró que no había candidato y no consultó test.
El test ya había sido consultado en trabajo histórico: no es un holdout virgen.

## Archivos solicitados y dónde encontrarlos

Las rutas de esta tabla son relativas a esta carpeta; `snapshot/` conserva las
rutas originales desde la raíz del repositorio.

| Solicitud | Ubicación / explicación |
|---|---|
| `data.yaml`, `dataset.yaml` | [Datasets](snapshot/outputs/classical_augmentation_v2/datasets): cada carpeta smoke/full contiene `data.yaml`. No se encontró un `dataset.yaml` adicional. |
| `args.yaml` y demás YAML | [Runs](snapshot/outputs/classical_augmentation_v2/runs), conservando fase, escenario y semilla. |
| `screening_summary.json` | [Resumen completo de screening](snapshot/outputs/classical_augmentation_v2/metrics/screening/screening_summary.json). |
| `confirmatory_summary.json` | [Resumen completo confirmatorio](snapshot/outputs/classical_augmentation_v2/metrics/confirmatory/confirmatory_summary.json). |
| `results.csv` | En cada corrida dentro de `snapshot/outputs/classical_augmentation_v2/runs/`. |
| `selection*lock*` | [Lock original, sin modificar](snapshot/outputs/classical_augmentation_v2/selection.lock.json). |
| `selected_scenarios*` | [Extracción directa del lock](extracted/selected_scenarios.json). |
| Manifiestos | En `datasets/{smoke,full}/<escenario>/manifests/derived_samples.jsonl`; también se incluyen `rejections.jsonl`. Son JSONL, no JSON/CSV. |
| Predicciones | [Screening](snapshot/outputs/classical_augmentation_v2/metrics/screening/prediction_cache) y [confirmación](snapshot/outputs/classical_augmentation_v2/metrics/confirmatory/prediction_cache). Cada JSON tiene una clave `predictions`; sus nombres son escenario/semilla, no `predictions*.json`. |
| Umbrales | [Screening](extracted/thresholds_screening.json) y [confirmación](extracted/thresholds_confirmatory.json): sweeps completos y punto seleccionado, extraídos sin recalcular. |
| Dificultad | [Screening](extracted/difficulty_screening.json) y [confirmación](extracted/difficulty_confirmatory.json): estratos originales por corrida, sin recalcular. |
| Entorno | `execution_environment.json`, `execution_environment_history.jsonl` y otros registros existentes dentro de cada fase en `runs/`. |
| `pip_freeze*`, `requirements*` históricos | No se encontraron en los outputs v2. No se inventó un freeze histórico ni se exportaron dependencias del proyecto Android ajeno a esta campaña. Usar las versiones efectivas en los registros de entorno. |
| `execution_state*` | `execution_state.jsonl` en las fases y diagnósticos dentro de `runs/`. |
| Previews / mosaicos | Ocho `preview_contact_sheet.jpg`, dentro de los [datasets completos](snapshot/outputs/classical_augmentation_v2/datasets/full). |
| Cierre de test | [Registro original](snapshot/outputs/classical_augmentation_v2/metrics/final_test/final_test_summary.json): `skipped_no_validation_selected_candidate`, `test_consulted=false`. |
| Perfil real y splits | [Perfil train-only](snapshot/outputs/classical_augmentation_v2/domain_profile/real_train_profile.json), con manifiestos de pertenencia y hashes de los tres splits. |

Los JSON grandes pueden requerir descarga mediante **Raw** en GitHub. No se
truncaron resúmenes ni predicciones para que cupieran en la vista web.

## No mezclar corridas válidas con intentos descartados

- Screening: 27 corridas incluidas (9 escenarios × 3 semillas × 30 épocas).
- Confirmación: 40 corridas incluidas (E0/E0R/E7 × 10 semillas; E3/E6 × 5;
  todas a 50 épocas).
- Se preservan otros 14 CSV de smoke, benchmarks e intentos descartados.
  No son 14 experimentos confirmatorios adicionales.
- En `quarantine_2026-08-27_duplicate_launcher/` están E0 seed05 con 99 filas
  y E3 seed05 con 82 filas: historiales intercalados por lanzadores duplicados.
  **No se usan en los resúmenes.** Las carpetas canónicas contienen las
  repeticiones limpias con épocas 1..50.
- El catálogo indica `included_in_summary` y `unique_epoch_prefix` para cada
  CSV. La pertenencia se toma del resumen original, no se infiere del nombre.
- E3/E6 tienen cinco semillas y los controles diez: comparar las diferencias
  emparejadas ya calculadas, no restar sus medias globales de distinta cohorte.
- Los tiempos de pared pueden incluir suspensiones o sólo un tramo reanudado.
  No interpretar automáticamente el campo `ultralytics_active_time_seconds`
  como tiempo puro de GPU sin interrupciones.

## Integridad y portabilidad

[inventory.json](inventory.json) enumera 384 archivos: 378 copias idénticas al
original y seis extracciones. Incluye ruta de origen, tamaño y SHA-256. Las
copias suman junto con las extracciones aproximadamente 151 MiB; el archivo
más grande es de unos 29 MiB. Esta guía y el propio inventario no se incluyen
recursivamente en su lista; quedan protegidos por el commit Git. El archivo
`.gitattributes` desactiva la conversión de finales de línea para preservar
los hashes al clonar en Windows o Linux.

Las rutas absolutas `C:/dev/SyntheticPlantGeneration/...` se preservan como
evidencia histórica. No funcionarán directamente en otro PC; la correspondencia
con los archivos exportados está en `inventory.json`. El hash del lock permanece
intacto porque no se reescribieron sus rutas. El verificador original del lock
requiere pesos y rutas locales que deliberadamente no se distribuyen aquí.

Desde la raíz de un clon del repositorio se puede verificar esta instantánea
con Python 3.11 o posterior, sin CUDA ni dependencias adicionales:

```powershell
python scripts/export_classical_augmentation_v2_review.py --verify --output artifacts/classical_augmentation_v2_review/2026-09-03
```

El exportador rechaza sobrescribir una instantánea existente. Una exportación
nueva debe ir a otra carpeta fechada y requiere acceso a los outputs originales.

## Alcance y derechos

Se incluyeron sólo resultados/metadata, configuración, informes y mosaicos
solicitados. Se excluyeron fotos individuales del dataset, labels TXT
individuales, checkpoints, binarios de entrenamiento y archivos Android.
Los mosaicos contienen ejemplos del dataset y conservan sus derechos originales;
su inclusión **no los relicencia bajo MIT**. El mismo criterio se aplica a los
datos de terceros presentes en manifiestos y anotaciones. Las copias exportadas
son evidencia experimental, no fuentes normativas del grafo de arquitectura.
