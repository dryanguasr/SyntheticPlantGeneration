# Campaña de vuelos de hilera — 20 de octubre de 2026

Autorizada por el usuario: comparar tres estrategias a unos 4 fps, hilera por ambos lados, vecinos de fondo, matrices de confusión y explicación de los fallos de cada video. No es un nuevo entrenamiento.

Se reutilizan sin modificaciones las plantas C06, C07 y C09 y los pesos finales del piloto congelado. Tres objetivos separados 3 m en una hilera, seis vecinos a ambos lados; suelo, cielo y materiales del generador congelado. Los parámetros espaciales son heurísticas de ingeniería, no medidas de un cultivo real. El antiguo piloto no se reabre.

Se conserva el marcador codificado de 20 cm (26,7 cm con margen); IDs distintos 8–13 por objetivo y cara. El aumento de marcadores y la disposición de instancias son configuración de la nueva escena, no cambios botánicos. La imagen frontal inicial muestra el arbusto completo, marcador y vecinos; ArUco8 se decodifica realmente. Comprobación trasera en ejecución antes de lanzamiento largo.

## Rutas predeclaradas

- Legacy: bordeado con encuadre completo y ArUco; 233 fotogramas, 58,25 segundos a 4 fps.
- Barrido vertical: aproximación al marcador y exploración inferior-superior de cada arbusto por ambas caras; 477 fotogramas, 119,25 segundos.
- Orbital: aproximación al marcador, vuelta completa cuando hay espacio y traslado al siguiente arbusto; 900 fotogramas, 225 segundos, repitiendo acceso desde ambos lados.

Total 1610 fotogramas. Trayectorias continuas con desplazamiento máximo por muestra de 0,125 m (0,5 m/s), clearance conservador de 0,35 m frente a cajas de plantas. Las seis órbitas pasan esta comprobación. No es simulación dinámica de dron, ni certificación de volumen de rotores; no incluye desenfoque físico calibrado. Las cajas se obtuvieron de la geometría congelada y se trasladaron con las instancias. No hubo reparaciones de colisiones entre plantas.

Las estrategias no tienen el mismo presupuesto temporal. El tránsito se registra separado de las fases de inspección. No se concluye superioridad a igualdad de tiempo a partir de sus totales.

## Evaluación y ejecución

Confianza 0,25, IoU nativo 0,5, detector congelado, ROI RGB heurística y parches 384/stride256 a entrada960. Matrices de verdad por predicción para todos los objetos y visibles con al menos100 píxeles y lado8 píxeles; criterio de ingeniería, no límite universal YOLO. También matrices del arbusto objetivo usando región privada de evaluación; no se presenta como selección automática. Exportación pública solo RGB y tiempo. Anotaciones raster originales exclusivamente para evaluador.

Por video se conservan máscaras, IDs predichos, H2644fps, matrices y ejemplos completos peor/mediano/mejor. Se separan errores de clase de omisiones y se cuantifica tamaño de los objetos omitidos. El área visible no determina oclusión. Las explicaciones causales no demostradas deben etiquetarse como hipótesis. Se revisará decodificación real por fase y asociación al objetivo.

Cola: outputs/row_flight_campaign_20261020/campaign_queue.py. Serializa bloques de20 renders, verificación, inferencia y evaluación. Un trabajo pesadoGPU, admisión6,5GiB, parada temprana3GiB para mantener reserva2GiB. Manifiesto de hashes propio e integridad heredada del piloto congelado. No usar semillas reservadas. Prueba de desarrollo sobre plantas vistas, no holdout externo.

Heartbeat horario: vuelos-de-hilera-tres-estrategias. Notificar entregables o fallos, no progreso rutinario. Tras verificar resultados y revisión visual, entregar informe y eliminar heartbeat.

## Presentación solicitada después del lanzamiento

Videos finales: vista principal del dron con máscaras e IDs, recuadro superior derecho de320×180 con render de tercera persona sincronizado a4fps. Proxy visual de dron únicamente en presentación; no altera imágenes, etiquetas ni métricas del detector. Se conservan videos originales. Scripts render_third_person.py y compose_pip.py se ejecutarán serialmente tras liberarGPU; verificar cada recuadro y duración antes del cierre.

## Siguiente etapa solicitada: entrenamiento a varias distancias (20 de octubre)

Después de probar y cerrar este piloto de vuelos, reentrenar con imágenes sintéticas capturadas a distancias cercanas, intermedias y lejanas. Es una solicitud explícita del usuario para mejorar robustez a escala; queda pendiente, no se inicia durante esta comparación. Mantener plantas y entorno aprobados, clases y máscaras originales; variar la cámara sin reabrir refinamiento botánico. El informe de cierre debe conservar este pendiente.

Los acercamientos deben ser nuevas capturas con cámara más cercana, no solamente recortes ampliados de vistas lejanas. Mantener un tamaño mínimo viable de los objetos y registrar su área visible y lado mínimo tanto en píxeles nativos como a la entrada del modelo. El criterio actual de 100 píxeles visibles y lado mínimo de 8 píxeles es una heurística de evaluación, no un límite universal de segmentación YOLO ni garantía de detectabilidad. Validar el criterio con entrenamiento/validación, sin ajustarlo sobre prueba; seguir reportando también todos los objetos y la cobertura excluida.

Revisar el tamaño de parche: comparar de forma controlada 384 y 640 píxeles con resolución de entrada declarada, contexto y truncamiento de instancias medidos. El flujo actual usa recortes nativos de 384 y entrada de 960; no se encontró una comparación que demuestre que 384 sea óptimo frente a 640. El código histórico de ROI usa parches de inferencia de 640, lo que no demuestra que todos los entrenamientos anteriores usaran recortes de ese tamaño. No confundir tamaño del recorte con resolución de entrada. Usar particiones por planta/escena y conservar resultados negativos; no promover mejoras basadas solo en métricas filtradas por tamaño.

Registro operativo: outputs/row_flight_campaign_20261020/next_campaign_multiscale_training_request.json. Esta solicitud no modifica protocolo, manifiesto, pesos ni ejecución activa.


## Cancelación explícita del usuario — 20 de octubre de 2026

Campaña cancelada, sin reanudación automática. El usuario va a suspender el PC y solicita retomar únicamente cuando avise, empezando por generar un dataset con tomas reales de cámara a diferentes distancias/profundidades y ángulos. Conservar plantas aprobadas, resultados parciales, negativos y logs. No continuar recuperación orbital ni renders PiP de esta campaña. El estado previo de fallo se conserva en state_before_user_cancellation.json; la cancelación no equivale a completar los entregables. Heartbeat eliminado.
