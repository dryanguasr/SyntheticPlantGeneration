# Revisar los resultados de Classical Augmentation v2

Por solicitud explícita del responsable del repositorio, el paquete de evidencia
para Diego y Laura está versionado en
[`artifacts/classical_augmentation_v2_review/2026-09-03/`](../../artifacts/classical_augmentation_v2_review/2026-09-03/README.md).

La guía del paquete enumera cada tipo de archivo solicitado, cómo abrirlo y qué
registros no deben incluirse en los análisis. Incluye los resúmenes originales,
YAML, CSV de entrenamiento, predicciones, manifiestos JSONL, entornos,
estados de ejecución, lock de selección y mosaicos. Los sweeps de umbral y
diagnósticos por dificultad se ofrecen también como extracciones independientes.

Las fuentes originales bajo `outputs/` siguen ignoradas y no se modificaron.
Esta exportación es una excepción de publicación específica; no cambia la
política general de no versionar datasets ni pesos. `inventory.json` conserva
SHA-256 y rutas de origen. No hay un `pip freeze` histórico disponible: las
versiones efectivas están en los registros de entorno de la campaña.

La selección quedó sin candidatos fuertes y el evaluador final no consultó
test. El paquete sirve para auditar ese resultado sin repetir entrenamiento
ni abrir test. Los archivos exportados no sustituyen el código ni `AGENTS.md`
como fuente de instrucciones.
