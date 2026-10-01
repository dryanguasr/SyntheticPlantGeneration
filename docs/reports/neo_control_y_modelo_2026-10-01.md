# Revisión de oscilaciones y modelo visual del Neo

Intervención iniciada el 30 de septiembre y cerrada el 1 de octubre de 2026.
Entorno: Gazebo Harmonic 8.14.0, WSL Ubuntu 24.04, D3D12/NVIDIA, Blender 5.1.2.
Campo morfológico semilla 230926, seis hileras, 36 plantas, 72 ArUcos,
sin plántulas triangulares. No se modificó la arquitectura botánica.

## Diagnóstico ejecutado

Se reprodujo la oscilación con un estacionario de 25 s, sin cultivo. El
criterio anterior comprobaba solo altura y marcaba éxito a pesar de la
oscilación lateral y angular. Ese resultado se conserva como evidencia
negativa; ya no se considera un estacionario estable.

El [controlador Lee de Gazebo](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/multicopter_control/LeeVelocityController.cc)
divide la ganancia de velocidad por masa. `3 3 4` en 135 g resultaba
demasiado agresivo para la dinámica configurada, con saturación frecuente
de la aceleración. Cambiar únicamente a `0.27 0.27 0.54` eliminó la
oscilación del estacionario; no se cambiaron motores, masas, inercias,
arrastre ni cámara. El parámetro `maximumLinearAcceleration` sí es leído
por la implementación: no era un error de nombre del campo SDF.

Se probaron tres configuraciones, además de una alternativa con mayor
amortiguamiento que no fue necesaria para la solución final:

| Ensayo | Alabeo RMS, 10–25 s | Cabeceo RMS, 10–25 s | Error 3D RMS, 10–25 s |
|---|---:|---:|---:|
| Control original instrumentado | 9,970° | 7,819° | 0,0964 m |
| Solo ganancia de velocidad escalada por masa | 0,000224° | 0,000124° | 0,00000183 m |
| Ganancia, transformación completa y rampa | 0,000086° | 0,000116° | 0,00000093 m |

Son ejecuciones en simulación ideal, sin viento ni ruido: los valores
cercanos a cero no implican precisión alcanzable por un DJI real. Cada
ensayo usa una ejecución, no una campaña estadística. El original alcanzó
17,99° de inclinación máxima. Se verificó después movimiento con traslación,
giros, seis hileras, retorno y descenso, no solo equilibrio simétrico.

La solución incorpora también transformación mundo→cuerpo mediante la
orientación completa, límite vectorial de velocidad horizontal y rampa
de aceleración de consigna. La ganancia se aisló primero; no se atribuye
su efecto a esos cambios adicionales. Se mantuvo la inercia de rotor
original porque la comparación no la identificó como causa principal.

## Anomalía independiente en la telemetría

En el primer recorrido corregido, a 124,576 s cambió el signo de los cuatro
componentes del cuaternión mientras la orientación física permanecía
continua. La odometría publicó un pico de unos −313 rad/s en yaw, incompatible
con el pequeño giro entre poses. La [implementación 8.14.0 de OdometryPublisher](https://github.com/gazebosim/gz-sim/blob/gz-sim8_8.14.0/src/systems/odometry_publisher/OdometryPublisher.cc)
calcula diferencias de cuaterniones sin resolver esa equivalencia de signo.

Se conserva `angular_velocity_raw_odom` y se calcula `angular_velocity`
desde poses consecutivas tomando el arco corto. Es una velocidad estimada
entre muestras, no un sensor IMU ni evidencia de estabilidad entre muestras.
El controlador interno de Gazebo usa velocidades físicas, no este twist
publicado: la anomalía no explica la oscilación original. Las cámaras no
recibieron filtros ni estabilización para disimular movimiento.

## Modelo y licencias

Se verificaron metadatos de [Sketchfab/Vanondemand](https://sketchfab.com/3d-models/dji-neo-0f602dff680c418393df3a2c61e45e43):
escaneo Polycam, 100 000 triángulos, CC BY-NC-SA 4.0, descarga con cuenta.
El visor incluye una mesa, por lo que no es directamente un CAD aislado.
La [malla de alphaviz en CGTrader](https://www.cgtrader.com/3d-print-models/hobby-diy/robotics/dji-neo-3d-printable)
era de pago y el autor la describe como aproximada, sin uso mecánico.
No se compró ni se importó ninguna de esas mallas. No se encontró un CAD
gratuito limpio y directamente utilizable en las fuentes revisadas.

El usuario prefirió reconstrucción propia desde fotografías. Se generó una
GLB original de 23 396 triángulos y se importó/adaptó mediante Blender a diez
mallas OBJ para Gazebo, incluyendo cuatro grupos de hélices animadas.
La referencia visual fue la [galería oficial DJI](https://store.dji.com/product/dji-neo).
La envolvente adaptada mide aproximadamente 130 × 157 × 48,5 mm, según las
[especificaciones DJI](https://www.dji.com/neo/specs); los detalles internos
son `engineering_heuristic`. Es una aproximación visual, no CAD del fabricante.

Carcasa redondeada, cámara y lente frontal, batería, rejillas elevadas,
protectores, motores y hélices de tres palas sustituyen las cajas anteriores.
La masa y los parámetros físicos permanecen separados de la malla. La
prueba unitaria compara el SDF completo después de retirar los visuales:
la sustitución no cambia dinámica, sensores ni colisiones. No se agregaron
dependencias. Código y geometría original son MIT; no se redistribuyen fotos.

## Evidencia y reproducción

Los comandos están en la [guía de vuelo](../guides/vuelo_neo_gazebo.md).
Salidas locales ignoradas, conservadas:

- `outputs/gazebo/controller_review/{baseline,mass_scaled,damped,corrected_hover}/`:
  SDF, misión, logs y telemetrías de 25 s. Los metadatos antiguos de las dos
  variantes aisladas aún dicen 0.1; los SDF contienen las ganancias efectivas.
- `outputs/gazebo/controller_review/comparison/`: métricas con hashes y gráfica.
- `outputs/gazebo/neo_field_flight_stable_v2/`: primer recorrido con control
  corregido y geometría anterior, 16/16 puntos, 149,702 s simulados, inclinación
  máxima 3,647°. Su métrica angular bruta tiene el defecto descrito arriba.
- `outputs/gazebo/neo_photo_model_v2/`: GLB, Blender editable, vista de revisión
  y fuentes. La versión v1 conserva un fallo al guardar la vista con ruta
  relativa; se corrigió usando ruta absoluta.
- `outputs/gazebo/neo_photo_visual_v3/`: OBJ, materiales, atribución y manifiesto
  con hash del GLB y transformaciones aplicadas.
- `outputs/gazebo/neo_photo_flight_v3/`: paquete del recorrido final con la
  malla refinada y telemetría de orientación completa.

Resultado final ejecutado: **16/16 puntos**, **149,702 s simulados**, 326,86 s
de pared, **3,648° de inclinación máxima** y 0,232 rad/s de velocidad angular
máxima combinada de alabeo/cabeceo estimada entre muestras. Longitud recorrida
90,58 m; altura en fases de hilera 3,292–3,585 m. Posición final aproximada
(−5,201; −5,603; 0,220) m: descenso completado según tolerancia, no aterrizaje.
`hover_settled: false` en este recorrido describe la ventana final en descenso,
no el ensayo de estacionario separado, que sí pasó.

El MP4 compuesto tiene 2246 fotogramas, 1280 × 720, 15 fps, H.264,
149,733 s y 32 575 675 bytes. Se decodificó completo con FFmpeg sin errores
y se inspeccionaron fotogramas a 15, 75 y 148 s. Ambas cámaras recibieron
2269 imágenes y codificaron 2246 según tiempo simulado. Se ve la nueva malla,
el cultivo y los ArUcos; el horizonte ya no presenta el balanceo fuerte
del ensayo original. Se conservaron `ffprobe.json` y `route_audit.json`.

Validación de código: **17 pruebas Gazebo aprobadas**, compilación sintáctica
de los scripts y grafo de contexto válido (140 nodos, 251 relaciones).
Las pruebas nuevas cubren ganancias por masa, transformación con inclinación,
rampas ante inversión de consigna, signo de cuaternión, rechazo de un
estacionario oscilante y separación entre malla visual y dinámica.

Se mantienen las limitaciones del ensayo anterior: odometría ideal,
propulsión no calibrada contra el Neo, ausencia de viento, colisiones
incompletas de plantas, cámaras ideales y descenso hasta tolerancia de
posición, sin demostrar aterrizaje/contacto. El modelo sirve para prototipar
el sistema de inspección; no valida un controlador para vuelo real.
