# Propuesta para un PR posterior: integración ROS 2

Estado **PROYECTADO**, sujeto a acuerdo de visión, brazo, locomoción y responsable de integración. No define aún mensajes, nombres de tópicos ni permisos de movimiento.

- Acordar contrato versionado de productores y consumidores: tipos, unidades, marcos, reloj, vigencia, errores, cancelación y compatibilidad.
- Proponer árbol TF y responsabilidades de calibración para cámara, plataforma y brazo; posiciones en metros, ángulos en radianes y transformaciones verificables. Definir diferencia entre tiempo de captura y publicación.
- Negociar QoS por intercambio, frecuencia, pérdidas, durabilidad y comportamiento ante desconexión; elegir mecanismos de comandos y confirmaciones tras analizar requisitos.
- Diseñar estados separados de objetivo detectado, aceptado, rechazado, comando, ejecución, fallo y cancelación, incluyendo correlación y expiración.
- Crear en ese PR un publicador XYZ de prueba, un receptor del brazo sin motores y un publicador de estado de locomoción, claramente identificados como dobles de prueba.
- Cubrir con `launch_testing` productor y consumidor: datos válidos e inválidos, timestamps vencidos o futuros, `frame_id` desconocido, TF ausente, fallos de comunicación y tiempos de espera. Registrar criterios de aceptación y evidencia independientes.

Ninguna recepción de prueba autoriza movimiento físico; la aceptación del contrato y la revisión de los tres equipos preceden su implementación.
