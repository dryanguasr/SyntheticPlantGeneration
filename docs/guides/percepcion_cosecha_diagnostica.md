# Percepción RGB y visibilidad nativa del piloto

La detección aprendida y la visibilidad privilegiada de Gazebo son dos fuentes
distintas. Los resultados no acreditan madurez interna, pose del pedicelo ni
percepción 3D autónoma. La selección de objetivos morfológicos sigue separada.

`uchuva_gazebo.harvest_perception.add_instance_observer` añade una pareja de
cámaras RGB/panóptica a un `world` SDF. Recibe nombre, pose xyz/rpy y los registros
`id`/`model_name` de los frutos seleccionados. Asigna una etiqueta semántica
distinta a cada modelo (máximo 254), sin mover superficies o modificar colisiones.
La etiqueta abarca la unidad reproductiva completa, incluido el pedicelo distal.
Las hojas y los frutos sin etiqueta siguen ocluyendo. El modelo de cámara es
pinhole con intrínsecos explícitos, iguales en ambos sensores.

`scripts/harvest_perception_capture.py::NativePerceptionRecorder` consume esa
configuración. Sólo guarda parejas con **el mismo timestamp nativo, en
nanosegundos**. Los PNG RGB y `frames.json` van en `public/`; las etiquetas y
`visibility.json` quedan en `private/`. El manifiesto público rechaza campos
adicionales, rutas fuera del paquete y cambios de SHA. Los píxeles visibles no
son una tasa de oclusión: falta el área amodal para calcularla.

El comando estático del mismo script fija explícitamente los modelos de una
copia y retira sus controladores, preservando geometría y poses. Es una captura
de sensores, no una ejecución física del robot. Su cierre registra el código
de salida real del servidor, incluso si hubo que terminar el proceso propio.

`scripts/harvest_rgb_tournament.py infer` sólo recibe paquetes RGB públicos y un
checkpoint con SHA esperado. Admite el ONNX end-to-end de 640 píxeles y los
segmentadores existentes mediante Ultralytics. Las vistas completas o los
parches exhaustivos de 640/stride 448 se fijan antes de inferir; no se seleccionan
regiones a partir de la verdad. Las propuestas guardan clase de apariencia,
confianza y caja; las supresiones de cajas entre parches quedan registradas.

El subcomando `evaluate` se ejecuta **después**, en otro proceso, y puede leer la
visibilidad privada. Empareja por ID de cuadro, timestamp y SHA RGB exactos. Si
sólo están etiquetados los objetivos, informa su cobertura; los demás capachos
no son falsos positivos conocidos. No calcula precisión global sobre verdad
incompleta ni convierte dos exposiciones de una misma vista estática en dos
escenas independientes.

Integración del criterio por objetivo:

```python
result = target_gate(
    prediction_row, visibility_row,
    mode=config["mode"],
    now_ns=current_native_stamp_ns,
    maximum_age_ns=config["maximum_age_ns"],
    minimum_visible_pixels=config["minimum_visible_pixels"],
    minimum_box_iou=config["minimum_box_iou"],
)
```

Todos los umbrales son explícitos. En `learned_rgb`, la presencia exige una
detección RGB y la asociación de identidad utiliza el simulador; esto se declara
como `RGB_detection_with_simulator_identity_association`. En
`gazebo_instance_visibility`, se pasa `prediction_row=None`: el resultado se
declara `privileged_native_Gazebo_visibility`. No existe cambio automático
silencioso entre modos. Un cuadro viejo, futuro o de otro hash no puede habilitar
un objetivo. El estado de visibilidad no sustituye alcance, trayectoria o
validación del mecanismo.

`scripts/harvest_perception_overlay.py::aligned_overlay` produce una copia
anotada del cuadro exacto. Distingue cajas RGB verdes y visibilidad nativa azul;
rechaza evidencia con otra identidad temporal. No se importa en la inferencia.

Los contratos puros se verifican con:

```text
python -m unittest discover -s tests -p test_harvest_perception.py -v
```
