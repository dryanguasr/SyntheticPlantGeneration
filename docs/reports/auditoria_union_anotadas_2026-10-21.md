# Auditoría de UNIÓN ANOTADAS — copia local y resultados

## Dictamen

**Copia local completa y auditoría técnica ejecutada. El conjunto sirve como base de desarrollo, pero las particiones actuales no son aptas para una evaluación independiente.** No se han modificado etiquetas, repartido imágenes de nuevo ni entrenado modelos.

Se descargaron **673/673 imágenes**, sin fallos, con **1.199.234.238 bytes** en total. Las 673 se decodifican y sus dimensiones coinciden con el manifiesto. Los conteos recalculados son 7.005 instancias y los mismos IDs publicados. Se encontraron **8 grupos de duplicados exactos entre splits**, **25 polígonos con cruces internos en 22 imágenes** y coincidencias visuales con la recolección local de septiembre.

## Identificación de la copia

- Carpeta: `outputs/datasets/union_anotadas_20261021_v1/`, excluida de Git.
- Versión **local**: `union_anotadas_20261021_local_v1`.
- Exportación preservada: `source_latest.ndjson`, 4.722.356 bytes; cabecera `version=latest`. **No se certifica identidad con la v1 publicada en la plataforma**: la descarga versionada del navegador no pudo recuperarse como archivo verificable. El sufijo local v1 identifica nuestra primera copia congelada por hash.
- SHA-256 del NDJSON: `3a73347a1f4aadeb78f78c82cac841435d379fb3d3758b08828f10c7e71c90cb`.
- La cabecera declara actualización `2026-10-22T03:58:41.112Z`, correspondiente al 21 de octubre en Bogotá.
- `download_manifest.json` registra fecha UTC, licencia declarada CC BY 4.0, fuente y SHA-256/tamaño/ruta de cada imagen. Se conservan nombres originales y número de fila; las rutas locales añaden la fila para impedir sobrescrituras por nombres repetidos.
- `integration_review.json` conserva el mapeo candidato, hashes del código de auditoría, bloqueos y estado `training_allowed=false`. Es un registro de revisión, no un guard implementado en los entrenadores.
- Rama existente: `codex/raster-supervision-v159`; HEAD al inicio `db4daaa441444f18e5dde1183ccb18ae9edd1f8f`. Se preservaron los cambios ajenos, sin commit ni publicación.

## Clases y particiones: medición local

| Partición | Imágenes | Pintona, ID 0 | Madura, ID 1 | Sobremadura, ID 2 | Instancias |
|---|---:|---:|---:|---:|---:|
| train | 468 | 3.724 | 740 | 349 | 4.813 |
| val | 135 | 1.128 | 232 | 109 | 1.469 |
| test | 70 | 571 | 102 | 50 | 723 |
| Total | 673 | 5.423 | 1.074 | 508 | 7.005 |

Distribución global: 77,4 %, 15,3 % y 7,3 %; razón mayoritaria/minoritaria 10,7:1. Hay 566/353/233 imágenes con cada clase, respectivamente; son conteos no excluyentes. Reportar métricas por clase y macro, además de localización colapsada, para evitar que Pintona domine la conclusión.

Las resoluciones son heterogéneas: predominan 1920×1080 (214), 4080×3060 (132), 1440×1440 (100), 3060×4080 (84), 3840×2160 (68) y 3072×4096 (52), junto a seis tamaños menos frecuentes. En una proyección con lado máximo 640, 16 instancias tienen un lado de caja inferior a 8 píxeles (14/1/1 por clase); es un diagnóstico geométrico, no un criterio de descarte. Hay 531 polígonos que tocan exactamente un borde; ello no demuestra truncamiento anatómico.

## Fugas y duplicados

Se verificaron **665 contenidos de imagen únicos** por SHA-256 de archivo y por hash de píxeles RGB decodificados. Ocho grupos, cada uno de dos copias, cruzan splits. Las etiquetas de ambos miembros son idénticas en esos ocho grupos.

| Cruce | Grupos | Filas del NDJSON, numeración desde 1 |
|---|---:|---|
| test–train | 3 | 23–244, 32–305, 47–414 |
| test–val | 3 | 10–568, 15–576, 49–634 |
| train–val | 2 | 81–546, 372–627 |

**6/70 imágenes de test (8,6 %) ya están en train o val.** No basta con quitar esas seis: existen posibles correlaciones de secuencia y más similitudes. dHash de 64 bits con distancia ≤5 detecta 17 pares candidatos en total, 13 entre splits; ocho de esos 13 son los duplicados exactos, otros cinco requieren revisión. Este umbral es un filtro de ingeniería, no una prueba de identidad ni una garantía de exhaustividad.

Hay 19 prefijos de nombres de tipo `prefijo_fNNNN.jpg`, 15 de ellos en varias particiones. Por ejemplo, `5d41efddf01cd412` aparece en train/val/test con 90/31/9 registros. Son **candidatos de agrupación por secuencia**, pendientes de confirmar contra los videos y sesiones de captura. La partición debe fijarse por grupo de adquisición antes de cualquier aumentación.

Se detectaron 14 grupos de nombres repetidos. Dos nombres se repiten dentro de test con URLs y anotaciones distintas (`245db87fe535f7da_f000000736.jpg` y `245db87fe535f7da_f000001036.jpg`). Sus archivos no son duplicados exactos; no deben fusionarse solo por nombre.

## Geometría y revisión visual

No se detectaron IDs inválidos, coordenadas no finitas/fuera de [0,1], segmentos con longitud inválida, polígonos de área nula, filas de anotación exactamente repetidas ni imágenes sin anotaciones. Se detectaron **25 cruces internos estrictos**, distribuidos en 19 instancias train, 5 val y 1 test, sobre 22 imágenes. El detector excluye contactos colineales; no certifica toda la topología.

Se inspeccionó una lámina determinista de 12 imágenes train que cubren las tres clases, y recortes de seis instancias train con cruces. Las máscaras visibles se refieren a capachos. Hay casos con trazos de unión entre regiones separadas y otros con pequeños bucles de contorno; los cruces no deben repararse automáticamente ni equipararse todos a igual gravedad. En las filas 155, 187 y 199 aparecen conexiones largas entre regiones que necesitan contrastarse con la anotación original y su representación de componentes desconectados.

Una comprobación adicional de rasterización nativa encontró intersección entre polígonos de distintas instancias en 303 imágenes; solo 15 superan el 1 % de la unión anotada. Se usó redondeo de coordenadas normalizadas por dimensión, recorte a los límites y `cv2.fillPoly`; resultados dependientes de esa convención, no verificación de la máscara original de la plataforma. **No es una tasa de oclusión.** Puede incluir bordes compartidos, imprecisión o diferencias visible/amodal, por lo que exige revisar el protocolo antes de resolver solapes.

La inspección es del agente para diagnóstico técnico. No sustituye revisión humana, acuerdo entre anotadoras ni validación de madurez del fruto. La muestra contiene variación marcada de color/luz dentro de clases; no se adjudicaron etiquetas nuevas.

## Relación con material previo

Se compararon 1.328 JPG de `Dataset Original/IMAGENES` y 668 imágenes de `Nuevo Dataset`. No hubo coincidencias exactas de bytes (ningún tamaño coincidía), lo que **no excluye reexportación o compresión**.

La comparación dHash encontró 218 imágenes históricas candidatas, todas bajo `Nuevo Dataset/Recolección de datos 12-09-2026`, vinculadas a 218 registros de esta exportación: 152 train, 40 val y 26 test. No hubo candidatos bajo el umbral en el dataset histórico monoclase. Se inspeccionaron tres pares train (filas 158, 479 y 269) y muestran las mismas escenas/fotografías que los originales de septiembre. Los restantes candidatos no están adjudicados. Esta nueva entrega anotada no debe presentarse automáticamente como una nueva adquisición externa nunca vista.

## Integración propuesta

1. Mantener esta copia íntegra como fuente; crear futuras revisiones en carpetas nuevas con hashes y procedencia. Preservar licencia/autoría y el baseline monoclase.
2. Solicitar el protocolo de Karen y Caroline y la correspondencia con sesiones/videos/plantas. El proyecto ya registró el 2 de octubre que las categorías se asignan por **apariencia del capacho**; no hace falta redefinir el objetivo. Falta comprobar las fronteras operativas y excepciones de esta anotación concreta, y si los polígonos son visibles/amodales o multiparte.
3. Crear una revisión adjudicada de los 25 polígonos y cinco pares similares adicionales, conservando las decisiones y originales. Confirmar grupos de captura y reconstruir splits por grupo; no prometer un holdout externo solo por reparar este reparto.
4. Congelar un diccionario explícito `0=Pintona, 1=Madura, 2=Sobremadura`, su versión y reglas. El orden coincide con `segmentation_cycles.CLASSES`, pero `class_for_grade(0..4)=0, 5=1, 6=2` sigue siendo una asignación sintética cuya equivalencia visual requiere contraste humano. Mantener `agronomic_maturity` desconocida cuando no exista medición pareada.
5. Conservar polígonos/máscaras por instancia y derivar cajas desde ellas cuando se requiera detección. El `RasterDataset` actual consume una imagen de IDs por píxel: **no convertir automáticamente polígonos solapados a ese formato**, porque perdería instancias en los solapes. Resolver el protocolo o usar planos de máscara independientes antes de construir el adaptador. No llamar «exact visible rasters» a una conversión aún no validada.
6. Después de superar esos controles, comparar real-only, sintético-only y mezcla bajo el mismo presupuesto y política de selección. Este trabajo no lanzó entrenamientos ni renders ni alteró la arquitectura botánica.

## Artefactos y comprobaciones

En la copia local: `audit/audit_report.json`, `images.json`, `instances.json`, `historical_overlap.json`, `raster_overlap.json`, `visual_sample.json`, `development_review.jpg`, `polygon_review.jpg`, `historical_train_pairs.jpg` e `integration_review.json` en la raíz. Los índices de instancia de los reportes comienzan en cero; las filas fuente comienzan en uno e incluyen la cabecera.

Scripts añadidos: `scripts/download_union_snapshot.py`, `scripts/audit_union_snapshot.py`, `scripts/compare_union_history.py` y `scripts/audit_union_overlap.py`. Pillow, NumPy y OpenCV ya estaban instalados; no se añadieron dependencias. Las comprobaciones de cruces y fuga entre splits tienen dos tests nuevos que pasan:

```powershell
& .venv-training/Scripts/python.exe -m unittest discover -s tests -p test_union_snapshot_audit.py -v
& .venv-training/Scripts/python.exe scripts/audit_union_snapshot.py outputs/datasets/union_anotadas_20261021_v1
& .venv-training/Scripts/python.exe scripts/audit_union_overlap.py outputs/datasets/union_anotadas_20261021_v1
& .venv-training/Scripts/python.exe scripts/compare_union_history.py outputs/datasets/union_anotadas_20261021_v1 'Dataset Original/IMAGENES' 'Nuevo Dataset' --perceptual
```

Se ejecutó `scripts/validate_repository_context_graph.py`: informa **10 localizadores de evidencia no encontrados** en guías/gobernanza preexistentes. El grafo ya tenía cambios ajenos antes de esta tarea y no se modificó. Los tests nuevos sí pasan; no se presenta el validador del repositorio como exitoso. Los primeros intentos de tests fallaron por invocación de un módulo `tests` no importable y luego por permisos del temporal del sandbox; se corrigió la invocación a discovery y la fixture usa un temporal dentro de outputs.

## Registro preliminar anterior — superado por los resultados anteriores

Fecha local: 2026-10-21 (America/Bogota). Estado: **descarga y auditoría de archivos pendientes por autenticación**. Este documento registra inspección de la interfaz pública, no resultados de una auditoría del ZIP.

## Fuente y versión

- Fuente: https://platform.ultralytics.com/uchuva-naranja/datasets/unin-anotadas
- Entrega atribuida por el usuario a Karen y Caroline; la interfaz muestra el espacio Uchuva Naranja y el nombre Diego Amaya. Conservar ambas procedencias sin inferir autoría individual de cada anotación.
- Licencia indicada: CC BY 4.0; conservar atribución y licencia en la copia, separadas de la licencia MIT del código.
- Versión publicada visible: **v1**, instantánea NDJSON anunciada como inmutable, 673 imágenes, 3 clases, 7.005 anotaciones; tamaño del NDJSON indicado: 1,1 MB. El conjunto con imágenes indica 1,1 GB. Son artefactos distintos.
- El botón de descarga del conjunto exige inicio de sesión. El intento de descarga de v1 devuelve `Unauthorized`. No se ha obtenido ningún archivo ni calculado hashes.

## Conteos publicados, aún no recalculados

| ID | Nombre exacto | Anotaciones | Imágenes con la clase |
|---|---|---:|---:|
| 0 | Pintona | 5.423 | 566 |
| 1 | Madura | 1.074 | 353 |
| 2 | Sobremadura | 508 | 233 |

Pintona representa aproximadamente el 77,4 % de las instancias, Madura el 15,3 % y Sobremadura el 7,3 %. La razón mayoritaria/minoritaria es aproximadamente 10,7:1. Las imágenes pueden contener varias clases; sus conteos no deben sumarse como imágenes distintas.

Particiones publicadas: train 468, val 135, test 70 (673 en total). Su independencia por planta, sesión o secuencia **no está verificada**. No se han ejecutado modelos ni usado estas particiones para selección.

## Compatibilidad preliminar con el código inspeccionado

`src/uchuva_lsystem/segmentation_cycles.py` define `CLASSES = ('pintona', 'madura', 'sobremadura')`: los IDs nominales coinciden con la interfaz, salvo capitalización. Su función `class_for_grade` asigna grados sintéticos 0–4 a clase 0, grado 5 a clase 1 y grado 6 a clase 2. Esta regla describe el generador; no acredita el criterio usado por las anotadoras.

`src/uchuva_lsystem/annotation_contract.py` separa apariencia candidata, observación humana y madurez agronómica. Mantiene revisión pendiente y clase de entrenamiento nula al preparar observaciones. `yolo_export.py` conserva el baseline monoclase. Ninguno fue modificado durante esta recepción.

La integración debe conservar el diccionario original y su hash, dominio real/sintético y procedencia por instancia. No convertir apariencia de capacho en madurez agronómica validada. La correspondencia semántica necesita el protocolo de Karen y Caroline: órgano delineado, máscara visible o amodal, criterio de transición/sobremadurez, tratamiento de ocultamiento, daño y ambigüedad. El acuerdo entre anotadoras requiere anotaciones independientes o una revisión específica; el conjunto fusionado por sí solo no lo mide.

## Trabajo pendiente al disponer de los archivos

1. Guardar exportación original y NDJSON v1 bajo `outputs/datasets/`, en directorio nuevo, con URL, fecha UTC, licencia, versión, SHA-256 del archivo y manifiesto de hashes. No sobrescribir originales ni incluir imágenes en Git.
2. Recalcular imágenes e instancias por clase y split; contrastar contra los conteos de la interfaz. Verificar diccionario y rutas del YAML/NDJSON.
3. Detectar imágenes corruptas, labels huérfanos/ausentes/vacíos, IDs fuera del diccionario, coordenadas no finitas o fuera de rango, polígonos degenerados, duplicados y anomalías geométricas. Diferenciar advertencias de errores; no reparar silenciosamente.
4. Comparar hashes exactos y similitud visual dentro y entre splits, además de metadatos de captura y posibles coincidencias con datos históricos. Una ausencia de duplicados exactos no demuestra independencia.
5. Revisar visualmente una muestra reproducible de desarrollo estratificada por clase, tamaño y carga, con superposición de máscaras. Registrar las imágenes examinadas y los casos para adjudicación humana. No ajustar el generador usando test.
6. Proponer un contrato común de segmentación y, si procede, cajas derivadas de máscaras para localización. Conservar baseline monoclase y separar métricas de localización de clasificación. No iniciar entrenamiento hasta resolver integridad y semántica.

No hay todavía copia versionada local, auditoría completa, validación humana ni integración ejecutada. La limitación actual es el acceso autenticado a la descarga.
