# Resultados generados

Esta carpeta no es autoridad del modelo y está ignorada por Git.

## Revisión actual

`current_review/` contiene el `.blend`, preview y reportes que deben abrirse
para revisar la iteración vigente.

## Diagnósticos vigentes

- `diagnostics/`: métricas puras.
- `diagnostic_renders/`: vistas estructurales.
- `human_validation/`: suites de diez casos y comparaciones antes/después.
- `reference_measurements/`: mediciones derivadas del dataset real.
- `datasets/`: datasets sintéticos y compuertas visuales reproducibles.
- `experiments/`: matrices derivadas para entrenamiento; nunca modifica el dataset real.

Resultados vigentes de esta iteración:

- `datasets/uchuva_original_synthetic_seed_1000_v1/`: dataset original de 100 imágenes.
- `datasets/uchuva_original_synthetic_seed_1000_v1_scale_calibrated/`: copia derivada para entrenamiento híbrido.
- `experiments/checkpoint_interpolation_scale80_seed_1000_v1/`: reporte y checkpoint final, seleccionado por validación natural.

## Histórico

`archive/` conserva escenas, blends, datasets piloto y pruebas previas. Los
nombres internos originales se mantienen cuando son necesarios para rastrear
la secuencia experimental; la carpeta padre indica que no son la versión
vigente.

`assets_cache/` es una caché descargable y regenerable.
