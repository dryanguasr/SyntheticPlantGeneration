# Campaña multiescala: entrega final de diagnóstico para las estudiantes

**22 de octubre de 2026 (UTC). Resultados sintéticos, sin promoción a producción.**

Empieza por [la guía PDF actualizada](guia_estudiantes.pdf) y descarga este directorio completo para abrir [el informe con videos y matrices](index.html) en un navegador. GitHub muestra el código HTML; no lo sirve como una web. Los MP4 también pueden descargarse y reproducirse directamente.

## Qué contiene

- Tres videos completos H264 a 4 fps, con máscaras/IDs desde el dron y vista externa sincronizada: [legacy, 44,5 s](videos/legacy_4fps_pip.mp4) [vertical, 41,75 s](videos/vertical_4fps_pip.mp4) y [órbita parcial, 70,5 s](videos/orbit_4fps_pip.mp4).
- Cuatro clips de diagnóstico anteriores, incluidos el barrido vertical que perdía encuadre y ambas versiones del recuadro de legacy. Se conservan como negativos, no como vuelos finales.
- Resultados completos de detección y seguimiento de las tres rutas nuevas, incluida la órbita parcial de 282 fotogramas. Su video con recuadro está incluido y revisado.
- Matrices globales, por elegibilidad, objetivo, fase, lado y planta; nueve ejemplos de vuelo seleccionados por regla predeclarada, y [18 ejemplos train/val del dataset con máscaras originales](dataset_sample/index.html).
- Métricas de entrenamiento y evaluación estática, pesos nuevo y de referencia, protocolos, auditorías, procedencia y fuentes de implementación.
- Los JSON completos de evaluación de las rutas están comprimidos **sin pérdida** en `evidence/flights/*_full_evaluation.json.gz`. Los archivos `metrics/{ruta}.json` omiten únicamente las listas largas `changes`, manteniendo métricas y casos por fotograma.

## Resultados principales

| Alcance | Referencia | Multiescala |
|---|---:|---:|
| F1, vistas completas de desarrollo | 51,34% | 59,86% |
| F1, elegibles de desarrollo | 68,38% | 76,98% |

Los elegibles son solo el 38,99% de las observaciones de desarrollo. El mAP50 de máscaras **43,14%** y mAP50-95 **18,15%** proceden de los 576 **parches de validación**, no de vistas completas ni vuelos.

| Inspección del objetivo C06/C07 | Legacy | Vertical | Órbita parcial |
|---|---:|---:|---:|
| F1 todos | 59,24% | 69,91% | 69,80% |
| F1 elegibles | 73,78% | 75,59% | 75,27% |
| Cambios ID / pares elegibles emparejados | 580/1054 | 1186/1447 | 2618/4272 |
| Tiempo de inspección | 10 s | 8,5 s | 21,25 s |

Las rutas tienen distintos presupuestos y vistas. Las tasas de cambios de identidad son condicionales, no IDF1/HOTA/MOTA. La localización 3D **ya se ejecutó y evaluó**; los informes `metrics/localization_*.json` contienen errores de cámara/capachos, cobertura y rechazos, con protocolo y evidencias en `evidence/localization`. ArUco8 mide 20 cm codificados y 26,67 cm con marco; C07 no tiene marcador propio.

## Uso e integridad

Desde este directorio:

```text
python verify_package.py
```

El verificador usa solo la biblioteca estándar. Comprueba todos los archivos sellados y los enlaces HTML locales. No lanza entrenamiento, Blender ni inferencia. `publication_manifest.json` registra tamaños y SHA256; `provenance.json` vincula las copias a sus fuentes originales. `.gitattributes` evita que Git convierta saltos de línea y altere los hashes.

`build_guide.py` reproduce el PDF con ReportLab y Pillow; usa Arial de Windows para la tipografía original. `guia_contenido.txt` conserva el texto fuente. `source_snapshot/` es una copia para lectura de las implementaciones usadas; contiene dependencias y rutas históricas y **no es una distribución autónoma del pipeline**.

Este paquete es un archivo de resultados y supervisión para análisis. `evidence/` contiene verdad y rutas privadas de evaluación: **nunca debe convertirse en el directorio de entrada del estimador**. El modelo recibe RGB y datos públicos permitidos; no máscaras, IDs verdaderos, poses exactas ni selección ROI por verdad.

Los datos masivos de las 384 vistas, los 627 fotogramas, los parches y todas las cachés permanecen en `outputs/` del equipo original; se publican sus contratos/manifiestos, ejemplos y evaluaciones, no un espejo de todo el dataset. No se incluyen credenciales ni entornos virtuales. Los checkpoints se incluyen por autorización expresa del usuario; su publicación no modifica los términos de los pesos y componentes de terceros. Consultar la licencia del repositorio y los avisos de Ultralytics.

## Cierre y limitaciones

Esta campaña terminó como diagnóstico. Todos los entregables previstos se ejecutaron y evaluaron, pero no se afirma el objetivo científico global ni se promueve el modelo a producción. Se conservan fragmentación de IDs, confusión de clase, casos sin triangulación, poses visuales incorrectas y el fallo antiguo de encuadre. El corte parcial anterior queda inmutable.

Solo datos sintéticos; topología compartida; prueba de desarrollo inspeccionada; ausencia de negativos completos; ruido sin sesgo ni deriva correlacionada y covarianzas heurísticas. Apariencia del capacho no es madurez interna. El centro AABB de su geometría no es el centro interno del fruto. La cobertura 3D es de mapa final, con errores condicionales y tracks fragmentados; no acredita navegación autónoma segura. La cara posterior del marcador y su patrón reflejable limitan la pose visual. El recuadro externo conserva legibilidad limitada por su tamaño.

La campaña cancelada `row_flight_campaign_20261020` continúa cancelada. No se modificaron plantas, entorno, marcador, detector o tracker para este cierre.

## Resumen 3D: fusión, objetivo elegible

| Ruta | Cámara mediana / P95 cm | Capacho mediana / P95 cm | Instancias únicas cubiertas |
|---|---:|---:|---:|
| legacy | 10,55 / 13,13 | 10,11 / 19,23 | 161/196 (82,14%) |
| vertical | 3,22 / 7,62 | 4,33 / 13,20 | 163/235 (69,36%) |
| orbit | 5,81 / 12,22 | 7,00 / 15,45 | 217/237 (91,56%) |

Referencia capacho: centro de caja 3D de geometría evaluada. No pose 6D ni madurez interna. Ver PDF para denominadores y criterios de atribución. Los archivos históricos de `evidence/context`, `evidence/dataset/state.json` y `report_assets` conservan el estado de sus cortes originales; `publication_status.json` describe el cierre actual.

Verificación de presentación: los tres MP4 H264 se decodificaron completos y se revisaron las selecciones predeclaradas de inicio/medio/final y cambios de fase. La apertura interactiva mediante la herramienta de navegador quedó bloqueada por su política para URLs `file:`; no se presenta esa comprobación como realizada. El PDF de 17 páginas se renderizó y revisó completo.
