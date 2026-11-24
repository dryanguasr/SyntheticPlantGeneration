# Piloto privado de segmentación con fotogramas y aumentación sintética

El control usa 461 fotos con máscaras privadas revisadas por el asistente. Los brazos sintéticos cambian 120, 240 o 600 de las 8.000 exposiciones y conservan la primera aparición de cada foto real. El brazo de encuadre usa 240 exposiciones y concentra las repeticiones en vistas más próximas al tamaño y densidad de los capachos reales. Comparte posiciones y reparto por escena con el brazo de 240 exposiciones sin prioridad. Cada brazo se ejecuta con las tres semillas del piloto privado anterior.

Las 115 vistas sintéticas proceden del banco corregido del 12 de noviembre. Se reconstruyen máscaras binarias por ID, a partir del raster nativo y de las clases de esa revisión. El paso de capacidad utiliza 2.032 instancias sintéticas y una foto real densa. Las máscaras se almacenan en RLE y las proyecciones al lienzo se guardan en una caché sin pérdidas.

## Ejecutar y recuperar

Usar el entorno local del piloto privado. La campaña histórica de renders debe permanecer pausada.

```powershell
$root = 'outputs/private_synthetic_masks_20261123'
$python = '.venv-training/Scripts/python.exe'
& $python scripts/prepare_private_synthetic_bank.py --output "$root/bank"
& $python scripts/run_private_synthetic_masks.py init --root $root
& $python scripts/run_private_synthetic_masks.py run --root $root
```

El controlador espera GPU, verifica la identidad de cualquier proceso pendiente y ejecuta un trabajador a la vez. Si se interrumpe, repetir el comando `run` con la misma raíz y las mismas fuentes. El trabajador valida el punto de control cada 500 actualizaciones. `state.json`, `active_child.json` y los logs indican la etapa y el progreso efectivo.

En paralelo, `scripts/audit_private_video_frames.py` prepara los candidatos, genera propuestas locales y sella las decisiones de revisión. El brazo de fotogramas se ejecuta si el manifiesto registra entre 20 y 60 fotogramas admitidos de al menos tres grupos corroborados, con un máximo de la mitad en un grupo. El piloto espera esa decisión antes de sellar todos los pesos y evaluar desarrollo.

## Sustituir las anotaciones reales

Preparar un manifiesto con una lista `train`. Cada fila conserva `id`, `image_sha256`, `width` y `height` del conjunto original y apunta a `annotation` y `annotation_sha256`. La anotación contiene `id`, `image_sha256`, `size`, `objects` e `ignore_regions`. Las máscaras nativas conservan huecos, fragmentos y solapamientos. Las regiones que no se puedan resolver conservan su estado de incertidumbre. Las fotos sin máscaras deben declarar el estado de supervisión.

Inicializar una raíz privada distinta con `--real-label-manifest` y el manifiesto humano completo. Preparar en ella la caché del mismo banco corregido con el primer comando de la guía. Esa preparación conserva la referencia original que fija el encuadre. Reutilizar `--frame-manifest` con la misma decisión sellada. El orden de exposición y las referencias de evaluación se derivan del mismo conjunto histórico. El controlador verifica cobertura, vínculo con el RGB y compatibilidad del lote con la supervisión.

## Comparar resultados

Consultar `report.md`, `summary.json` y `gallery/` dentro de la raíz privada. Cada contraste usa el mismo umbral operativo del control de su semilla, elegido sobre las 88 fotos de validación. Las 94 fotos de desarrollo ya se consultaron en estudios anteriores. El AP de máscaras, las omisiones y las confusiones describen desempeño frente a esas referencias históricas. Los paquetes de los estudiantes y el informe privado se distribuyen por separado.
