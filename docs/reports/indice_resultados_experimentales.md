# Resultados experimentales para edición

Corte al **24 de noviembre de 2026**. Este índice reúne los pilotos ejecutados, los resultados negativos, los estudios bloqueados y las comprobaciones técnicas que condicionan su lectura. Las etiquetas describen la **apariencia visible del capacho**. Los trabajos que comparten fotografías, grupos de captura o modelos inicializados con las mismas semillas tienen evidencia correlacionada.

## Segmentación de instancias

- [Escalera de 20 a 461 fotos y piloto con sintéticas y fotogramas](resultados_segmentacion_privada_2026-11-24.md). Dos estudios de 18 corridas cada uno, tres semillas, 88 fotos de validación y 94 de desarrollo histórico. La dosis de 240 exposiciones sintéticas ganó 1,42 puntos de AP macro de máscaras frente al control en desarrollo. El brazo de fotogramas ganó 0,92 puntos en desarrollo y bajó 0,20 en validación. Las máscaras del asistente se usaron como referencia provisional de entrenamiento.
- [Campaña de segmentación raster de octubre](cierre_campana_segmentacion_2026-10-04.md). Comparación de ciclos, segmentación multiescala y diagnóstico de instancias pequeñas bajo su propio protocolo.
- [Campaña multiescala, informe parcial](campana_multiescala_20261021_parcial_v1/README.md) y [cierre de datos y vuelos](campana_multiescala_final_v1/README.md). Resultados en imágenes, video y localización métrica con el protocolo histórico de cada etapa.
- [Protocolo de revisión cruzada](../guides/auditoria_ciega_segmentacion.md). Describe el procedimiento previsto para obtener máscaras humanas adjudicadas.

### Tablas reproducibles de los dos estudios de noviembre

| Tabla | Filas de datos | Contenido |
|---|---:|---|
| [Métricas por semilla](datos_segmentacion_2026-11-24/metricas_por_semilla.csv) | 72 | AP50 y AP50–95 de máscaras, soporte y errores al umbral operativo por brazo, semilla y partición |
| [Métricas por estrato](datos_segmentacion_2026-11-24/metricas_por_estrato.csv) | 2.304 | Soporte y AP por clase, lado equivalente o grupo de captura |
| [Exposiciones por semilla](datos_segmentacion_2026-11-24/exposiciones_por_semilla.csv) | 36 | Imágenes, pasos, tiempo registrado y apariciones de instancias por clase y origen |

El AP, la precisión y la sensibilidad se almacenan como fracciones de 0 a 1. Una celda vacía representa una métrica indefinida, por ejemplo una clase sin referencias en un estrato. Los tamaños usan el lado equivalente obtenido de la raíz cuadrada del área de la máscara, a escala de entrada de 960 px. Los grupos están numerados dentro de cada partición. La columna `politica_umbral` distingue calibración por modelo y calibración emparejada con el control real. Las exposiciones cuentan cada aparición en entrenamiento, incluidas repeticiones. Los tres controles del piloto sintético reprodujeron las predicciones de validación del extremo de 461 fotos de la escalera.

## Detección, generación y percepción robótica

- [Pilotos de detección y generación de octubre y noviembre](resultados_pilotos_deteccion_y_generacion_2026-11-24.md). Contrastes de detección, controles reales, diagnósticos de Sobremadura, banco pausado y factores de apariencia cuyo entrenamiento quedó bloqueado.
- [Screening de aumentación clásica v2](aumento_clasico_v2_screening_2026-08-25.md), [campaña de cinco semillas](campana_aumento_clasico_5_semillas_2026-08-21.md) y [cierre confirmatorio de clásica v2](aumento_clasico_v2_confirmatory_2026-08-28.md). Conservar en la edición los criterios operativos junto con el AP y el resultado final de selección.
- [Admisión espacial de plantas](plantas_admision_espacial_8h_2026-10-29.md), [banco de cultivo admitido](dataset_cultivo_admitido_2026-10-29.md) y [auditoría científica del generador](auditoria_generacion_sintetica_2026-10-25.md). Evidencia de generación, auditoría y cobertura de captura.
- [Curación del dataset de campo](curacion_nuevo_dataset_2026-09-22.md), [evaluación en video](evaluacion_video_continuo_2026-10-08.md) y [cierre de localización 3D](cierre_localizacion_3d_2026-10-05.md). Cobertura de adquisiciones, detección continua y localización bajo sus referencias.
- [Validación del piloto de cosecha en Gazebo](piloto_cosecha_desmontable_validacion_gazebo_2026-10-31.md). Resultados simulados con sus condiciones de escena y las limitaciones de la evaluación.

Para las tablas del manuscrito, conservar por separado AP de cajas, AP de máscaras, métricas de seguimiento y errores métricos 3D. Identificar explícitamente las particiones históricas de desarrollo y las comparaciones exploratorias. La publicación reúne resultados agregados. Las fotos, máscaras individuales, pesos, predicciones y material de revisión estudiantil se custodian por separado.
