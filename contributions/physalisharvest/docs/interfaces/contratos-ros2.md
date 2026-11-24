# Contratos ROS 2: propuesta para acordar

**Estado:** propuesta conceptual; no existen en esta base mensajes, tópicos, servicios ni acciones implementados. Los nombres y campos siguientes no constituyen una interfaz definitiva. Los equipos de visión, brazo y locomoción deben acordarlos y versionarlos antes de implementarlos en `robot_interfaces`.

| Intercambio propuesto | Emisor → receptor | Contenido a acordar |
| --- | --- | --- |
| Observaciones y objetivo seleccionado | visión → brazo | Identificador de observación y fruto, XYZ en metros, `frame_id`, instante de captura, vigencia, calidad e incertidumbre o motivo de rechazo. |
| Aproximación candidata | visión → brazo | Identificador del objetivo y de la propuesta, puntos o poses, orden, marco, tiempo y vigencia. El brazo evalúa viabilidad; una propuesta no autoriza movimiento. |
| Estado del manipulador y respuesta | brazo → visión / coordinación | Identificador de comando o propuesta, aceptado/rechazado/en ejecución/completado/error, motivo y tiempo. |
| Estado de plataforma y posicionamiento | locomoción ↔ coordinación | Pose y marco, instante, estado de movimiento, disponibilidad, comandos y confirmaciones correlacionadas; semántica pendiente. |

## Decisiones necesarias

- Identificar nombres, tipos de mensajes y tópicos, emisores, receptores, QoS, frecuencia, formato, versionado y compatibilidad; decidir cuándo usar tópicos, servicios o acciones.
- Expresar XYZ en metros y acordar convención de ejes, marcos de cámara, brazo y plataforma, `frame_id` y árbol TF. Definir responsables y fuentes de transformaciones, calibración, incertidumbre y comportamiento si falta una transformación o es obsoleta.
- Acordar reloj, timestamp de adquisición, sincronización, validez máxima, política de datos tardíos y ausencia de datos. No confundir hora de publicación con captura.
- Definir selección, identidad, cancelación, pérdida de objetivo, trayectoria y criterios de rechazo; distinguir datos válidos, inválidos, desconocidos, rechazados y errores con causas explícitas.
- Definir comandos, identificadores de correlación, confirmaciones, tiempos de espera, reintentos, cancelación y estados terminales; el receptor debe validar cada orden y su contexto.
- Acordar reglas de seguridad, arbitraje y límites antes de cualquier movimiento; ninguna detección, trayectoria o confirmación de transporte constituye validación física.

Registrar decisiones, ejemplos y pruebas de compatibilidad acordadas en este directorio antes de crear archivos `.msg`, `.srv` o `.action`.
