# Prueba de vuelo del Neo aproximado sobre el cultivo

## Modelo y fuentes

Se buscó un DJI Neo importable el 28 de septiembre de 2026 y se revisó de nuevo
el 30 de septiembre / 1 de octubre. Se encontraron:

- [DJI neo de Vanondemand en Sketchfab](https://sketchfab.com/3d-models/dji-neo-0f602dff680c418393df3a2c61e45e43),
  escaneo Polycam de 100 000 triángulos. En la segunda revisión se verificó
  CC BY-NC-SA 4.0 mediante la API oficial; la descarga pide iniciar sesión.
  El visor muestra también una mesa: requiere recorte y no es un CAD limpio.
- [DJI NEO de alphaviz en CGTrader](https://www.cgtrader.com/3d-print-models/hobby-diy/robotics/dji-neo-3d-printable),
  comercial (US$6 en la consulta), OBJ/FBX/STL, aproximado según el autor.
  No se compró: el usuario prefirió una reconstrucción propia desde fotos.
- [DJI Neo de too3D en TurboSquid](https://www.turbosquid.com/FullPreview/2284418),
  comercial y con indicación de uso editorial. No se compró.

También apareció un [modelo con formatos CAD anunciados en 3DModels](https://3dmodels.org/3d-models/dji-neo/),
pero no se obtuvo un archivo gratuito ni se verificó su calidad geométrica.
No se encontró en la búsqueda un paquete SDF/URDF del Neo listo para vuelo.
Esto no demuestra que no exista. Los modelos anteriores son referencias
visuales, sin dinámica DJI verificada. No se copiaron mallas de terceros.

Se creó `uchuva_gazebo.neo`, una aproximación original con cuerpo, batería,
cámara, cuatro hélices y protectores abiertos. La envolvente usa **130 × 157 ×
48,5 mm y 135 g**, según [DJI, especificaciones del Neo](https://www.dji.com/neo/specs).
Las formas internas, distribución de masa, inercias, constantes de motor,
arrastre y ganancias son `engineering_heuristic`. No corresponden a mediciones
del drón ni al firmware del fabricante.

## Qué simula

La trayectoria se ejecuta mediante cuatro `MulticopterMotorModel` y el
controlador [MulticopterVelocityControl de Gazebo](https://gazebosim.org/api/sim/8/classgz_1_1sim_1_1systems_1_1MulticopterVelocityControl.html).
El controlador calcula velocidades de rotor; los motores aplican empuje en
la simulación física. El seguidor de puntos envía velocidades en el marco del
cuerpo a `/neo/cmd_vel`, usando `/neo/odometry` como estado ideal. No se mueve
el drón por llamadas a `set_pose`. No hay estimación visual, GPS simulado,
autopiloto DJI/PX4/ArduPilot, viento ni enlace de radio.

El recorrido despega fuera del campo, asciende a **3,4 m**, barre las seis
hileras en serpentina, retorna por fuera y desciende sobre el punto inicial.
La altura supera el cable de tutorado de 2,5 m. No es una inspección cercana
del capacho ni una ruta certificada para vuelo real. El criterio de llegada
es 13 cm de error de posición y 0,15 rad de error de orientación; las
limitaciones de colisión de la copa siguen vigentes.

Se graban dos cámaras ideales:

- `onboard.mp4`: cámara a bordo, inclinada 0,65 rad hacia abajo.
- `chase.mp4`: cámara de seguimiento para ver el modelo y su recorrido.

Ambas publican RGB 1280 × 720 y se codifican a 15 fps. El campo horizontal
de 90° es una elección de simulación; no se afirma equivalencia con la
óptica o estabilización real del Neo. FFmpeg remuestrea según el sello de
tiempo simulado: si falta una muestra, mantiene la anterior y registra
cuántos fotogramas se recibieron y codificaron. El video no representa
el tiempo de pared consumido por la simulación.

## Reproducir

Se usan Blender, Gazebo Harmonic, sus bindings Python y FFmpeg ya instalados.
No se añaden dependencias al núcleo morfológico. Todos los directorios de
salida de estos comandos deben ser nuevos.

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.1/blender.exe' -b --python scripts/simplify_gazebo_field.py -- --source outputs/gazebo/field_v2 --output outputs/gazebo/mi_lod --ratio .12
.venv-training/Scripts/python.exe scripts/batch_gazebo_field.py --source outputs/gazebo/mi_lod --output outputs/gazebo/mi_campo_aereo
.venv-training/Scripts/python.exe scripts/prepare_neo_flight.py --field outputs/gazebo/mi_campo_aereo --output outputs/gazebo/mi_vuelo
```

En Ubuntu/WSL:

```bash
cd /mnt/c/dev/SyntheticPlantGeneration
python3 scripts/run_neo_flight.py outputs/gazebo/mi_vuelo
python3 scripts/compose_neo_flight_video.py outputs/gazebo/mi_vuelo/flight
```

En esta máquina se verificó también `--graphics wsl-d3d12`, que selecciona
D3D12 y el adaptador NVIDIA solo para ese proceso. El modo EGL predeterminado
eligió llvmpipe por software y resultó demasiado lento. La opción D3D12
requiere WSLg, `/dev/dxg` y los controladores existentes; no los instala.
La salida de ese ensayo se conserva en `outputs/gazebo/neo_field_flight_gpu_v1/`.

El paquete contiene `neo_approx.sdf`, `flight.sdf` y `mission.json`. El mundo
referencia las mallas del paquete LOD vecino: ambos deben trasladarse juntos.
El primer LOD reduce la geometría visual, no la distribución botánica; conserva
ArUcos y colisionadores. La agrupación aérea posterior reúne 543 mallas y las
placas en 21 lotes por color; conserva las superficies y patrones de esos
marcadores. Para esta misión elevada mantiene únicamente colisiones de suelo,
placas, postes y cables superiores. No simula contactos con plantas ni cuerdas
verticales. La tabla de órganos del paquete reducido registra
identidad de origen, no rangos de triángulos después de la simplificación.

La carpeta `flight/` recibe videos, telemetría, puntos alcanzados, log del
servidor y `result.json`. Comprobar `completed: true` y los 16 puntos
alcanzados; un video parcial por sí solo no acredita un recorrido completo.
`vuelo_neo_cultivo.mp4` combina el seguimiento con una ventana de la cámara
a bordo. El compositor rechaza ensayos incompletos.
El primer ensayo parcial lento está en `outputs/gazebo/neo_field_flight_v1/`;
la misión optimizada está en `outputs/gazebo/neo_field_flight_v2/`.

Para la prueba corta de estacionario, preparar otro paquete con `--no-crop`
y ejecutar `run_neo_flight.py ... --probe-seconds 25`. Desde la versión 0.2
exige al menos 10 segundos y comprueba los últimos 5: error tridimensional
menor de 5 cm y RMS de alabeo/cabeceo menor de 1°. No basta la altura.

## Malla propia basada en fotos e importación futura

`scripts/build_neo_visual.py` crea una malla original usando como referencia
las [fotos de la tienda DJI](https://store.dji.com/product/dji-neo): carcasa
redondeada, batería, cámara, lente, protectores, rejillas y hélices de tres
palas. Exporta GLB y un `.blend` editable, además de una vista de revisión.
Los detalles internos son estimados; no es CAD mecánico del fabricante.
La geometría original es MIT; las fotografías de referencia no se redistribuyen.

`scripts/adapt_neo_visual.py` importa esa GLB, selecciona objetos, centra la
envolvente, aplica **escala uniforme** y exporta OBJ con normales, colores y
atribución. También admite una malla externa local OBJ/STL/FBX/GLB/glTF.
STEP necesita exportación previa desde una herramienta CAD, sin instalar
conversores automáticamente. Los colores base se conservan; las texturas
no se transfieren. Una proporción incompatible con la envolvente detiene
la adaptación para revisar orientación y selección de objetos.

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.1/blender.exe' -b --python scripts/build_neo_visual.py -- --output outputs/gazebo/mi_neo_modelo
& 'C:/Program Files/Blender Foundation/Blender 5.1/blender.exe' -b --python scripts/adapt_neo_visual.py -- --input outputs/gazebo/mi_neo_modelo/neo_photo_reference.glb --output outputs/gazebo/mi_neo_visual --author 'SyntheticPlantGeneration contributors' --license MIT --source-url https://github.com/dryanguasr/SyntheticPlantGeneration/blob/codex/gazebo-uchuva-field/scripts/build_neo_visual.py --source-kind original_photo_reference --reference-url https://store.dji.com/product/dji-neo --animated-rotors
.venv-training/Scripts/python.exe scripts/prepare_neo_flight.py --field outputs/gazebo/flight_batched_v1 --visual-package outputs/gazebo/mi_neo_visual --output outputs/gazebo/mi_vuelo_refinado
```

`--animated-rotors` separa objetos `rotor_0_*` a `rotor_3_*` en las cuatro
articulaciones existentes. Para un modelo externo sin esa separación, omitir
la opción: su representación visual completa será rígida, aunque los cuatro
motores físicos seguirán activos. Usar autor y licencia reales del archivo,
sin aplicar MIT automáticamente a materiales de terceros.

El cambio visual no modifica masa, inercias, motores, colisiones ni sensores.
Los activos generados siguen fuera de Git. El paquete final de esta iteración
es `outputs/gazebo/neo_photo_flight_v3/`.

## Control y comprobación de estabilidad

Gazebo divide `velocityGain` por la masa. Los valores anteriores `3 3 4`
implicaban aproximadamente `22,2 22,2 29,6 s⁻¹` en un vehículo de 0,135 kg.
La versión 0.2 usa `0,27 0,27 0,54`, equivalentes a `2 2 4 s⁻¹`, conservando
las ganancias de actitud y las inercias del ensayo original. La prueba
aislada y sus limitaciones están en el [informe de revisión](../reports/neo_control_y_modelo_2026-10-01.md).

`flight_control.py` contiene funciones puras para `R(q)ᵀ v`, limitación de
aceleración de consigna a 0,5 m/s² y rampa de velocidad de giro. La inclinación
superior a 25° aborta la prueba; una misión con máximos de 15° o más no pasa
la aceptación. Son umbrales de ingeniería para este ensayo, no límites DJI.

La telemetría conserva cuaternión, alabeo, cabeceo, velocidad lineal de cuerpo,
consigna y velocidad angular bruta de odometría. También calcula velocidad
angular de intervalo usando el arco corto entre cuaterniones, invariante
ante `q → -q`; evita interpretar cambios de representación como giros reales.
No se modifica Gazebo ni se usa esta corrección para ocultar movimiento.
Las cámaras siguen rígidas al cuerpo, sin estabilización añadida.

`scripts/analyze_neo_stability.py` compara telemetrías, guarda hashes y métricas.
`--plot` usa Matplotlib solo si ya está disponible; no es dependencia del
control ni del generador morfológico. `--no-video` en el ejecutor permite
ensayar toda la misión sin codificar RGB. `hover_settled` se interpreta solo
en un estacionario: el final de una misión que está descendiendo no lo exige.
