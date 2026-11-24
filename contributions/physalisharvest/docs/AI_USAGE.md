# Registro de uso de IA

El 19 de noviembre de 2026, Codex preparó el paquete y la documentación del banco ROS 2 en `ros2_ws/src/robot_locomocion/bench_2wd/`. El responsable suministró el montaje y la referencia de calibración. La verificación de software y sus límites se entregan con el cambio. El ensayo físico y la revisión humana quedan pendientes.

En esta etapa se utilizó Codex para diseñar e implementar verificadores locales, pruebas y esta documentación. La revisión humana, los acuerdos entre equipos y la aceptación del cambio están pendientes. Las verificaciones ejecutadas y sus limitaciones se informan en la entrega; la referencia estructurada figura en `ai_usage.json`.

También se utilizó Codex para preparar el workflow de CI y su documentación. La ejecución en GitHub, la revisión humana y la aceptación siguen pendientes hasta contar con evidencia real.

La primera ejecución del PR #2 completó estáticos y resumen; el job ROS omitió compilación y pruebas por no haber paquetes. Codex preparó correcciones de la puerta de pruebas ROS y una propuesta de integración posterior; su revisión humana y evidencia de ejecución actualizada quedan pendientes.

La segunda ejecución del PR demostró el fallo y la corrección en el paquete temporal de CI; la validación ROS del robot y la revisión humana siguen pendientes.

Codex asistió en la estructura documental de los subsistemas y el entorno de referencia; los requisitos fueron suministrados por el responsable y la revisión humana está pendiente.

Codex asistió en la corrección del estado de CI del README principal solicitada por el responsable; la revisión humana está pendiente.

Codex asistió en la política de sincronización y verificaciones Git; revisión humana y adopción pendientes.

Codex asistió en la clasificación de rutas y el procedimiento de sincronización solicitado; revisión humana pendiente.

Codex asistió en los cambios de nomenclatura, CI, verificador de contexto Git, pruebas y documentación de PhysalisHarvest. El responsable definió los requisitos y conserva la revisión e integración. Los resultados se registran en el PR de migración.

Registro de integración del 19 de noviembre de 2026. ChatGPT asistió en la preparación de `AGENTS.md`, `CONTRIBUTING.md` y `README.md` v2. El responsable seleccionó y copió las versiones al clon local. Codex auditó su coherencia, comprobó la integridad y la sintaxis Mermaid, preparó correcciones mínimas y ejecutó los verificadores y las pruebas unitarias para el PR documental. La revisión y la fusión corresponden al responsable.

El 19 de noviembre de 2026, Codex asistió en el banco 2WD, la captura y el análisis puntual de calibración, el transporte ROS/USB, los sketches y clientes de diagnóstico, y la consolidación de los registros textuales. El operador confirmó el cableado declarado, supervisó la alimentación y el corte, preparó las mediciones y observó el giro. [Resultados y límites](../firmware/bench_2wd/README.md).

El 19 de noviembre de 2026, Codex preparó el visor ArUco de solo diagnóstico, su documentación y el script que codifica con OpenCV los marcadores sintéticos 0, 1 y 2. El responsable definió las indicaciones de corrección y la parada a 0,50 m. [Uso del visor](../ros2_ws/src/robot_locomocion/bench_2wd/README.md#visor-local-aruco).

El 20 de noviembre de 2026, Codex adaptó el banco ArUco al DRV8833,
modificó el armado ROS 2, preparó el lanzador Python y documentó la
reproducción desde un clon. El operador suministró el cableado y pidió
la auditoría sin ensayos físicos. [Procedimiento y evidencia](../ros2_ws/src/robot_locomocion/bench_2wd_drv8833/README.md)

El 20 de noviembre de 2026, Codex implementó la consola Windows, el
monitor ROS y una escena sintética para la vista previa. La herramienta
integrada de generación de imágenes produjo el emblema de cáliz, fruto y
chasis de dos ruedas. El operador pidió mostrar solo el símbolo en la
cabecera. El PNG fuente conserva la atribución. La escena de vista previa
es una ilustración por OpenCV y se identifica como simulación.

El 20 de noviembre de 2026, Codex implementó la ruta ArUco configurable
y el escaneo de cinco segundos. El responsable definió el orden inicial
y pidió verificarlo con cámara y ESP32 desconectados. Se usaron datos
sintéticos y transporte MOCK.

El 20 de noviembre de 2026, Codex revisó los giros por el desenfoque
reportado por el operador. Implementó PWM para corrección y sondeo,
pulsos de búsqueda sin límite total y el estado Esperando ArUco.
La verificación se limitó a software con datos sintéticos y GPIO/serial MOCK.

El 20 de noviembre de 2026, Codex ajustó la transición de sondeo a avance
tras el reporte de parada al detectar el marcador en el piso. El operador
pidió un mínimo de 85 % de PWM durante el movimiento y menor PWM en
corrección que en avance. Se agregaron pulsos de alineación y pruebas
con coordenadas sintéticas, sin ensayo físico de este cambio.

El 20 de noviembre de 2026, a petición del operador, Codex configuró V4
al 100 % de PWM en ambas ruedas durante avance, corrección y sondeo.
El puente y la consola distinguen V4 de las compilaciones V3. La
verificación de salidas y comunicación se realizó con GPIO y USB MOCK.

El 20 de noviembre de 2026, Codex ajustó el control ROS a pulsos de
100 ms y pausas de 500 ms por solicitud del operador. Añadió la
confirmación del centro con dos cuadros nuevos y probó esa transición
con datos sintéticos y sin actuación física.

El 20 de noviembre de 2026, Codex separó el ArUco visible sin profundidad
local de una captura inválida y añadió a V5 un ajuste de avance para la
deriva a la derecha reportada por el operador. El ajuste inicial se
verifica en software. Su calibración física queda pendiente.
