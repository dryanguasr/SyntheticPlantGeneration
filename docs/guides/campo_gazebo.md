# Campo de uchuva en Gazebo Harmonic

La línea iniciada el 28 de septiembre de 2026 replica la distribución del piloto
disperso: 6 × 6 uchuvas, tutorado superior y 72 ArUcos `DICT_4X4_100`.
No genera plántulas triangulares ni vegetación contextual. La arquitectura vegetal
procede del JSON morfológico; Blender solo interpreta sus órganos y evalúa las
mallas. No se convierte un `.blend` ni se usa el prototipo genérico.

La escena se entrega en metros, Z arriba: las 8 unidades originales equivalen
a un metro. Separaciones de 1,4 m entre plantas, 1,8 m entre hileras y cable a
2,5 m siguen siendo `manual_initial_guess`, no mediciones del cultivo real.
El lado negro del ArUco es 10 cm, su margen blanco 2 cm. Su reverso es opaco.

## Generar el mundo

Requiere Blender ya instalado y el input morfológico del piloto. No instala
dependencias. El directorio de salida debe ser nuevo para evitar mezclas.

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.1/blender.exe' -b --python scripts/export_gazebo_field.py -- --input outputs/sparse_overhead_pilot_v7/scene_00/input.json --markers outputs/sparse_overhead_pilot_v7/markers --output outputs/gazebo/mi_campo
```

`field.sdf`, `meshes/*.obj` y `manifest.json` forman un paquete portable.
El directorio `meshes/` incluye también `surface.mtl`, necesario al trasladarlo.
El manifiesto registra semilla, preset, SHA-256 del input, conversión de escala,
órganos de origen y mallas. Los colores son planos: no reproduce los shaders
procedurales de Blender. Las geometrías foliares y reproductivas conservan su
forma evaluada; agrupar por material no redefine la botánica.

## Ejecutar y verificar en Ubuntu/WSL

Con Gazebo Harmonic instalado:

```bash
cd /mnt/c/dev/SyntheticPlantGeneration
python3 scripts/check_gazebo_field.py outputs/gazebo/mi_campo/field.sdf
```

La prueba valida SDF, arranca un servidor aislado por `GZ_PARTITION`, recibe dos
imágenes reales mediante Gazebo Transport y cierra su propio servidor. Guarda
PNG y logs en `smoke/`. No es un render Blender ni una validación del drón.

Para explorar interactivamente:

```bash
cd /mnt/c/dev/SyntheticPlantGeneration/outputs/gazebo/mi_campo
export GZ_SIM_RESOURCE_PATH="$PWD${GZ_SIM_RESOURCE_PATH:+:$GZ_SIM_RESOURCE_PATH}"
gz sim -r field.sdf
```

Los tópicos son `/uchuva/overview/image` y `/uchuva/drone_camera/image`.
Las cámaras publican RGB 1280 × 960 a 5 Hz de simulación, FOV horizontal 60°.
Son cámaras ideales de inspección, con poses configurables en SDF; no corresponden
a una calibración del DJI. Gazebo emplea +X hacia delante en el enlace de cámara;
OpenCV emplea +Z óptico hacia delante. No confundir ambas convenciones.

El servicio `/world/uchuva_field/set_pose` permite mover `drone_camera` durante
la ejecución para explorar vistas. Esto desplaza una cámara estática, sin
dinámica de vuelo, autopiloto ni protocolo de radio. El siguiente paso es
conectar el modelo del drón y su control a este mundo, conservando los tópicos
de percepción y la escala métrica.

La primera salida local comprobada está en `outputs/gazebo/field_v2/` y las
capturas reales de Gazebo en `smoke/`. Es una versión detallada de unos
16 millones de triángulos; se observó un consumo del servidor de unos 13 GB
durante la carga. No se ha validado tiempo real. Antes de integrar vuelo,
se recomienda reducir el LOD visual y medir tasas y latencias.

## Física y cosechador

El suelo, las placas, los ejes primarios y el tutorado tienen colisión simplificada.
Las hojas, ramas laterales y capachos son visuales. No usar este LOD para afirmar
seguridad de trayectorias dentro de la copa. El cilindro de los postes aproxima
su sección rectangular. No hay viento, flexión dinámica, masas medidas ni
desprendimiento; esos contratos quedan para el cosechador.

La identidad de órganos se conserva en el manifiesto, pero no se publica aún
segmentación semántica desde Gazebo. Las advertencias del input morfológico
siguen vigentes: esta exportación no certifica ausencia de intersecciones.
La madurez agronómica permanece desconocida y la validación humana pendiente.

Referencias técnicas: [sensores en Harmonic](https://gazebosim.org/docs/harmonic/sensors/),
[renderizado sin interfaz](https://gazebosim.org/api/sim/8/headless_rendering.html),
[SDFormat 1.9](https://sdformat.org/spec/1.9/sdf/).
