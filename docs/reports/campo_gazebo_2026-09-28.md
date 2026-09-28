# Primera réplica del campo en Gazebo — 2026-09-28

Se abrió `codex/gazebo-uchuva-field` después de guardar el trabajo previo en
`2f260c1` y publicarlo en `origin/codex/annotation-packages-20260925`.
La nueva línea fue solicitada para preparar simulación del drón y,
posteriormente, del cosechador.

## Artefacto generado y ejecución nueva

La salida local es `outputs/gazebo/field_v2/field.sdf`, con sus mallas y
`manifest.json`. Deriva de `outputs/sparse_overhead_pilot_v7/scene_00/input.json`,
semilla 230926, preset `sparse_overhead_strings_v1`. El SHA-256 del input se
registra en el manifiesto. Se reconstruyeron mallas desde la morfología,
sin abrir los `.blend` anteriores. No se generó un lote de imágenes de entrenamiento.

- 36 plantas en seis hileras, 72 ArUcos `DICT_4X4_100`, sin plántulas triangulares
  ni vegetación contextual.
- 543 lotes de malla por material; 15.990.454 triángulos.
- 2.280 objetos de capacho con identidad de origen en el manifiesto.
- 2.996 colisionadores estructurales; adicionalmente, suelo y 72 placas.
- Mundo métrico, Z arriba; conversión explícita de 8 unidades originales por metro.

Se ejecutó **Gazebo Harmonic 8.14.0 en Ubuntu 24.04/WSL** y Ogre2 sin GUI.
`gz sdf -k` devolvió `Valid.`. Las cámaras publicaron RGB 1280 × 960 mediante
Gazebo Transport; se guardó el sexto fotograma recibido de cada una, con sello
de simulación en el JSON. Las imágenes son producidas por Gazebo, no Blender.
El ensayo inicial completo queda en `smoke_initial_framing/`; el encuadre
panorámico se corrigió después para mostrar el campo completo.
La segunda ejecución completa también pasó y sus capturas definitivas están
en `smoke/`; volvió a detectar 0, 14, 26 y 54 en la cámara cercana.

En la captura cercana del ensayo completo, OpenCV detectó los IDs
**0, 14, 26 y 54**. La vista general no produjo detecciones por su escala;
no se afirma que los 72 marcadores sean simultáneamente visibles o detectables.
El servidor no registró errores de carga de mallas en ese ensayo. Ogre2 emitió
advertencias sobre bits reservados de máscara de visibilidad, sin impedir RGB.

Ocho pruebas del puente/campo Gazebo y cuatro del grafo pasaron; el validador
del contexto reportó 138 nodos y 249 relaciones. Antes del respaldo pasaron
35 pruebas de piloto disperso, paquetes, reanudación y visión de escritorio.
No se reejecutaron pruebas Android ni la campaña Blender histórica completa.

## Resultados negativos y correcciones

La primera exportación parcial (`field_v1`) se interrumpió al detectar nombres
incorrectos de dimensiones de poste; permanece ignorada por Git. La exportación
completa corregida usa `section_width` y `section_depth`.

La prueba de una planta cargaba demasiados subobjetos y mostraba superficies
blancas. Se conservaron los nombres de órganos en comentarios OBJ y manifiesto,
se agrupó cada lote por material, se añadieron MTL y normales explícitas.
El ensayo posterior confirmó superficies iluminadas y detección del ArUco 0.
`runtime_probe/` y `mesh_probe/` conservan las salidas de comprobación locales.

## Límites y continuación

Es una réplica geométrica aproximada del piloto, no un gemelo medido del campo.
Las distancias siguen siendo `manual_initial_guess`. La madurez agronómica
es desconocida y la revisión humana permanece pendiente. Las advertencias
morfológicas originales no se convierten en una certificación de colisiones.

La cámara cercana es un soporte de inspección estático movible por servicio,
no un drón con dinámica, autopiloto o radio. No hay todavía ROS/PX4/ArduPilot,
controlador de vuelo ni modelo específico del DJI. Las hojas, ramas laterales
y capachos no colisionan en este LOD. El cosechador necesitará contratos de
contacto y desprendimiento con incertidumbre explícita.

La versión detallada es pesada: una observación durante la carga registró
13.170.608 KiB de RSS del servidor. No es una medición de pico ni una prueba de
tiempo real. Los 5 Hz son la frecuencia de simulación configurada, no un
rendimiento de pared validado. Antes del control de vuelo conviene crear y
comparar un LOD visual reducido, manteniendo intactos los patrones ArUco y
las referencias métricas; luego integrar el robot y medir latencia, tasas y
colisiones relevantes. Los shaders procedurales de Blender no se exportan.

Comandos reproducibles en [la guía del campo](../guides/campo_gazebo.md).
