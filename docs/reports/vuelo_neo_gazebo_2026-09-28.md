# Vuelo del Neo aproximado y video completo — 2026-09-28

Se ejecutó una misión dinámica de barrido del campo con un modelo aproximado
del DJI Neo. La búsqueda encontró modelos visuales de terceros, pero no un
paquete de vuelo Gazebo verificable; no se descargaron activos con licencia
desconocida ni se compraron modelos. Las fuentes y alternativas están en
[la guía de vuelo](../guides/vuelo_neo_gazebo.md).

## Modelo y ejecución nueva

La envolvente de 130 × 157 × 48,5 mm y la masa de 135 g proceden de DJI.
El modelo visual es propio y sencillo. Inercias, distribución de masas,
propulsión, arrastre y ganancias son aproximaciones de ingeniería. Se usan
cuatro motores físicos `MulticopterMotorModel` y `MulticopterVelocityControl`;
el seguidor recibe odometría ideal de simulación y manda velocidades. No hay
teletransporte de poses ni firmware DJI.

Primero pasó una prueba de estacionario de 12 s simulados. La última muestra
antes de terminar registró z = 1,177 m para un objetivo de 1,2 m; el error
tridimensional era 0,115 m. Esa prueba solo verifica convergencia de altura.

La misión completa está en `outputs/gazebo/neo_field_flight_gpu_v1/`:

- Semilla del campo: 230926; seis hileras, 36 plantas, 72 ArUcos.
- 16/16 puntos alcanzados: ascenso, entrada/salida de cada hilera, retorno
  exterior, regreso al punto inicial y descenso.
- Duración de simulación registrada: 131,954 s; ejecución de pared: 327,416 s.
- Altura durante las pasadas por hileras: 3,268–3,405 m.
- Longitud integrada de la trayectoria muestreada: aproximadamente 99,96 m.
- 3.882 muestras de telemetría; estados de cada punto alcanzado guardados.
- Posición final aproximada: (-5,230, -5,620, 0,219) m. El criterio de
  descenso se alcanzó dentro de la tolerancia de 13 cm respecto a z = 0,10 m;
  no se validó contacto de aterrizaje con el suelo.

La GPU utilizada fue `D3D12 (NVIDIA GeForce RTX 4050 Laptop GPU)`, comprobada
en el log de Ogre. El backend y la selección de adaptador se aplicaron solo
al proceso de prueba. No se instalaron dependencias ni controladores.

## Video y verificación

`flight/vuelo_neo_cultivo.mp4` combina la cámara de seguimiento con una ventana
de la cámara a bordo. Se conservan `chase.mp4` y `onboard.mp4` completos.

El MP4 combinado mide 1280 × 720, usa H.264 y dura **132 s**, con 1.980
fotogramas a 15 fps. Se recibieron 2.000 mensajes RGB por cámara y se
remuestrearon por tiempo simulado. No se utilizó el tiempo de pared como
velocidad de reproducción. La decodificación completa con FFmpeg pasó.
Se revisaron visualmente fotogramas a 15, 65, 115 y 131 s: modelo visible,
campo cargado, ventana a bordo y recorrido/retorno coherentes.

SDF válido y sin errores de carga en el log del ensayo completado. Pasaron
11 pruebas del puente/campo/Neo, incluyendo conservación de masa, capacidad
de empuje, cobertura de las seis hileras e índices de mallas agrupadas.
El grafo del repositorio valida con 140 nodos y 251 relaciones.

## Ensayos parciales y optimización

La malla visual pasó de 15.990.454 a 1.919.708 triángulos mediante decimación
de Blender. Después se agruparon 543 lotes y las placas ArUco en 21 mallas
por color, conservando las superficies de esa versión y los patrones de
marcador. Para el vuelo sobre tutorado se retuvieron solo colisiones de
suelo, placas, postes y cables superiores; los contactos con plantas y
cuerdas verticales no se simulan.

Los ensayos `neo_field_flight_v1` y `neo_field_flight_v2` se interrumpieron
por bajo rendimiento del backend EGL/llvmpipe: completaron respectivamente
1 y 2 puntos en 229 y 292 s de pared. Conservan videos parciales, logs y
telemetría. Sus reportes dicen `completed: false`; la interrupción manual
ocurrió antes de incorporar el registro explícito `operator_interrupted`.
Una prueba GLX sin selección de controlador también eligió llvmpipe.
La prueba D3D12 inicial eligió Intel y produjo un cierre con core al vencer
el timeout; la ejecución NVIDIA completa terminó y cerró normalmente.

## Alcance

Es una prueba de trayectoria y percepción sintética con dinámica aproximada.
No valida comportamiento del Neo real, viento, radio, estimación visual,
estabilización DJI, seguridad de vuelo entre copas ni cosecha. Ambas cámaras
están ligadas al cuerpo, de modo que el horizonte refleja la inclinación del
vehículo; no se emula el gimbal ni RockSteady. La reducción visual no altera
el JSON botánico original ni convierte estados sintéticos en madurez real.
