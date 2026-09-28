# Prueba de vuelo del Neo aproximado sobre el cultivo

## Modelo y fuentes

Se buscó un DJI Neo importable el 28 de septiembre de 2026. Se encontraron:

- [DJI neo de Vanondemand en Sketchfab](https://sketchfab.com/3d-models/dji-neo-0f602dff680c418393df3a2c61e45e43),
  anunciado como descargable; la página devolvió 403 y no se obtuvo un archivo
  con licencia verificable en esta sesión.
- [DJI NEO de alphaviz en CGTrader](https://www.cgtrader.com/3d-print-models/hobby-diy/robotics/dji-neo-3d-printable),
  comercial y disponible en varios formatos visuales. No se compró.
- [DJI Neo de too3D en TurboSquid](https://www.turbosquid.com/FullPreview/2284418),
  comercial y con indicación de uso editorial. No se compró.

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
y ejecutar `run_neo_flight.py ... --probe-seconds 12`. Esa prueba verifica
convergencia de altura; no equivale a validar la misión completa.
