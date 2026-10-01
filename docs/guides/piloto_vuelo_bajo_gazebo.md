# Piloto de vuelo bajo y localización respecto a ArUcos

Esta línea ejecuta inspección lateral de `plant_12`–`plant_23` manteniendo las
36 plantas y el tutorado originales. La verdad de referencia conserva los IDs
reproductivos del generador morfológico. No usa el campo agrupado del vuelo alto.

## Preparación y puertas de ejecución

1. `scripts/prepare_low_flight.py` recupera cada capacho desde los comentarios
   `# source` de la exportación original. Conserva sus triángulos, materiales,
   todas las hojas y los 2.996 colisionadores originales. Comprueba los 747
   capachos objetivo y los 2.280 del campo. No se decima ni se cambia textura.
2. `scripts/audit_low_flight_clearance.py`, ejecutado con Blender, consulta las
   superficies triangulares mediante BVH, además de los cilindros de colisión
   y cajas. Una esfera que encierra completamente al Neo cubre cualquier
   actitud. Muestrea el recorrido cada ≤1 cm y resta la corrección de Lipschitz
   para certificar el segmento continuo. El límite de exclusión espacial de
   triángulos también se registra. No es una comprobación de vértices aislados.
3. `scripts/run_low_flight.py --technical` ejecuta 10 segundos. Al crear el
   vehículo suspendido hay un transitorio de arranque de motores en el extremo
   exterior. El avance comienza cuando recupera la altura. El arranque queda
   registrado y separado de las pasadas evaluadas.
4. `scripts/validate_low_capture.py` comprueba sellos, proyección de etiquetas,
   altura, velocidad y separación de las poses ejecutadas. Usa la propiedad
   Lipschitz de distancia a obstáculos y las muestras de la auditoría original
   para obtener cotas en las poses observadas. Conserva una corrección temporal;
   no afirma observar movimiento no muestreado con resolución infinita.
5. `scripts/freeze_low_pilot.py` registra hashes de configuración, SDF, modelo,
   controlador de misión, inferencia y método multivista. El vuelo completo
   comprueba esos hashes y exige la aprobación técnica. No cambia umbrales
   según el resultado del detector.

El monitor de recorrido reserva 1 cm adicional antes del mínimo de 15 cm.
Si no se cumple la separación, se detiene la ejecución, conservando el campo.
Los giros y cambios de altura se realizan en x = ±4,6 m. La cámara tiene 90°
de campo horizontal, 1280 × 720 píxeles y 20° hacia abajo. Los mandos máximos
son 0,16 m/s horizontal y 0,08 m/s vertical; se verifica la velocidad ejecutada
frente al techo de 0,20 m/s durante las pasadas.

La corrección lateral es independiente de la distancia longitudinal al destino.
Normalizar todo el vector hacia un punto lejano reducía demasiado la corrección
de deriva lateral; el primer ensayo completo se abortó por ese motivo y se
preservó en `outputs/gazebo/low_pilot_v1/flight`. La segunda variante usa
`src/uchuva_gazebo/low_flight_control.py`, con una prueba de regresión específica.

## Canales de datos

- RGB y segmentación panóptica Gazebo usan cámaras coincidentes a 15 Hz.
  Se selecciona la exposición original común más cercana a cada instante de
  la cuadrícula de 5 Hz. Los sellos deben ser exactamente iguales; los pares
  faltantes se registran y excluyen. Los MP4 nunca son entrada del evaluador.
- Cada capacho es un modelo estático separado, con clase panóptica 1 y nombre
  de longitud fija. Ogre2 ordena los nombres de visuales en orden descendente;
  el inventario registra el contador de instancia esperado. La prueba técnica
  verifica las etiquetas contra los límites proyectados de sus mallas.
- `evaluator/inventory.json`, máscaras y poses de cámara interpoladas desde
  odometría son exclusivos del evaluador. Las poses interpoladas tienen su
  intervalo registrado. El primer fotograma anterior a la primera odometría
  se excluye de la comprobación de proyección.
- `scripts/export_low_rgb_inputs.py` publica únicamente RGB, sellos y
  calibración/parámetros de estimación. El estimador no recibe inventario,
  máscaras, poses Gazebo ni posiciones verdaderas de marcadores.

La interpretación de las etiquetas corresponde a Gazebo Harmonic / Ogre2:
[asignación de nombres](https://github.com/gazebosim/gz-rendering/blob/gz-rendering8/ogre2/src/Ogre2Visual.cc)
y [contador panóptico](https://github.com/gazebosim/gz-rendering/blob/gz-rendering8/ogre2/src/Ogre2SegmentationMaterialSwitcher.cc).
La proyección verificada es necesaria para detectar incompatibilidades de versión.

## Estimación y evaluación

`scripts/estimate_low_flight.py` reutiliza `VisionEngine` de la app: letterbox
640² RGB, confianza 0,25, salida end-to-end, sin NMS adicional. Mantiene el hash
`19b6de32788952d77ee842cd4a1d5895212cf6f7b90d7c441f31357c392be4ca`.
Solo se evalúa capacho, nunca madurez.

`src/uchuva_gazebo/multiview.py` usa IPPE con lado negro de 0,10 m. Rechaza
soluciones con profundidad negativa, reproyección >3 px o ambigüedad entre
poses distintas con diferencia de error <0,25 px. Estos valores son heurísticos.
Asocia cajas mediante flujo LK ida/vuelta, al menos tres puntos fiables, y
correspondencia uno a uno; rechaza candidatos ambiguos y competencia entre
trayectorias. No une marcos de distintos marcadores. Triangula con tres o más
observaciones, ángulo ≥3° y error máximo de reproyección ≤3 px.

La homografía planar conserva la convención X hacia la derecha del marcador,
Y hacia arriba, sin estimar profundidad. La 3D añade Z saliente del marcador.
Las observaciones rechazadas y las detecciones sin localización se conservan.

`scripts/evaluate_low_flight.py` es el único paso que une estimaciones con IDs
verdaderos. Deriva cajas del soporte visible, separa objetos con <16 píxeles
y usa correspondencia uno a uno IoU ≥0,5. Los resultados ajenos a las doce
plantas se separan; se conservan FP, FN y duplicados. La precisión por planta
no se inventa atribuyendo FP sin correspondencia a una planta arbitraria.
La cantidad de píxeles visibles no se denomina fracción de oclusión.

## Comandos del paquete preparado

```powershell
.venv-training/Scripts/python.exe scripts/validate_low_capture.py outputs/gazebo/low_pilot_v2
.venv-training/Scripts/python.exe scripts/freeze_low_pilot.py outputs/gazebo/low_pilot_v2
wsl -d Ubuntu-24.04 -- bash -lc 'cd /mnt/c/dev/SyntheticPlantGeneration && python3 scripts/run_low_flight.py outputs/gazebo/low_pilot_v2'
.venv-training/Scripts/python.exe scripts/validate_low_capture.py outputs/gazebo/low_pilot_v2 --run flight
.venv-training/Scripts/python.exe scripts/export_low_rgb_inputs.py outputs/gazebo/low_pilot_v2
outputs/desktop/venv/Scripts/python.exe scripts/estimate_low_flight.py --rgb outputs/gazebo/low_pilot_v2/flight/rgb --frames outputs/gazebo/low_pilot_v2/flight/rgb_frames.json --config outputs/gazebo/low_pilot_v2/flight/estimator_config.json --output outputs/gazebo/low_pilot_v2/flight/estimates
.venv-training/Scripts/python.exe scripts/evaluate_low_flight.py outputs/gazebo/low_pilot_v2 --estimates outputs/gazebo/low_pilot_v2/flight/estimates
```

Las salidas son locales e ignoradas por Git. Las pruebas técnicas fallidas se
preservan. Un resultado pobre es válido como resultado exploratorio: no autoriza
reentrenamiento, cambios de textura o sensores adicionales retrospectivos.
