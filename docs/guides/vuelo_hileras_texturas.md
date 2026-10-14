# Inspección cercana de las doce caras del cultivo v4

Esta línea usa la morfología `individual_bouquet_crown_v4` y el Neo dinámico
existente. Conserva las 36 plantas, sus posiciones, los ArUcos y el tutorado.
No reentrena el detector ni modifica sus umbrales. Es una exploración de
dominio sintético, no una evaluación externa de desempeño real.

## Exportación de apariencia

`scripts/export_gazebo_field.py --textures` conserva las UV por esquina de
triángulo; la generación de normales conserva sus índices y costuras. Usa los
mapas locales de `assets/textures/current/` para color y rugosidad. El puente
anterior descartaba UV y mapas, dejando solamente colores planos. No se
reproduce todo el shader de Blender ni se añaden fotografías nuevas.

El material PBR usa metalicidad cero. No se exporta el mapa normal en esta
prueba: aislar color y rugosidad evita mezclar el efecto de un relieve tangente
no verificado. Los siete grados sintéticos conservan su identidad y usan
variantes verdes, de transición, pajizas y secas de la biblioteca existente;
eso no valida madurez agronómica.

Referencia de implementación:
[materiales PBR de SDFormat](https://gazebosim.org/api/sdformat/13/classsdf_1_1SDF__VERSION__NAMESPACE_1_1PbrWorkflow.html).

`--visual-lod` reduce solamente la geometría renderizada. Conserva los órganos
y UV, pero no certifica fidelidad geométrica milimétrica. La auditoría de
recorrido construye las mallas originales completas desde la morfología,
independientemente de ese LOD. No se retiran obstáculos para habilitar pasillos.

## Recorrido y comprobaciones

`audit_bouquet_rows.py` evalúa las dos caras de cada hilera a 0,65 / 0,80 /
0,95 / 1,10 m. Los caminos rectos están a 0,9 m del eje de hilera; los giros y
traslados se realizan en X = ±4,8 m, fuera de los extremos. Incluye la malla
completa de cada planta y tutorado, el suelo y, al preparar el paquete, los
paneles de marcadores. El margen descuenta la esfera envolvente del Neo y
2 cm por muestreo continuo. Se requiere 15 cm y se reserva al menos 18 cm
en el plan. El control monitoriza el margen ejecutado con la cota de Lipschitz
de las distancias verdaderas muestreadas. Si baja de 15 cm se detiene el ensayo.

La cámara es ideal: 1280×720, 15 fps, campo horizontal de 60° y 15° hacia abajo.
Es una lente de inspección declarada, no una calibración de DJI. La velocidad
de referencia horizontal está limitada a 0,16 m/s. El Neo se mueve por motores
y controlador, no mediante cambios directos de pose. Las cámaras de la prueba
A/B sí se colocan directamente, en escenas estáticas separadas del vuelo.

## Prueba A/B del detector congelado

Se capturan 24 vistas, dos posiciones por cara de hilera. El control principal
compara color plano dentro de PBR con albedo texturizado, manteniendo iguales
geometría, cámara, iluminación y mapa de rugosidad. El material antiguo sin PBR
se conserva como diagnóstico separado: cambió la cobertura visible de máscaras
y no sirve para aislar causalmente el efecto del albedo.
Gazebo entrega RGB y máscaras panópticas con el mismo sello simulado. Se
comprueba IoU de silueta de máscaras ≥0,999 entre cada par antes de comparar.

`natural_hybrid_alpha_045`, SHA-256
`19b6de32788952d77ee842cd4a1d5895212cf6f7b90d7c441f31357c392be4ca`,
usa el motor de la app, letterbox 640×640, confianza 0,25 y salida end-to-end
sin NMS adicional. El detector recibe sólo RGB; las máscaras se usan después
para coincidencias uno a uno con IoU ≥0,5 y referencias con ≥16 píxeles.
Se conservan resultados negativos y falsos positivos. Son observaciones
por vista, no conteos de capachos únicos ni prueba de generalización real.

El vuelo guarda RGB originales a aproximadamente 1 Hz para diagnóstico,
además de video a 15 fps y telemetría. Los fotogramas repetidos del MP4 no se
usan como observaciones independientes. Las detecciones del vuelo completo,
sin máscaras, no se presentan como precisión o recall.

## Entradas y comandos

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.1/blender.exe' -b -t 4 --python scripts/export_gazebo_field.py -- --input outputs/bouquet_crowns_v4/input.json --markers outputs/sparse_overhead_pilot_v7/markers --output outputs/gazebo/bouquet_v4_textured --individual-calyces --textures --visual-lod
& 'C:/Program Files/Blender Foundation/Blender 5.1/blender.exe' -b -t 2 --python scripts/audit_bouquet_rows.py -- --input outputs/bouquet_crowns_v4/input.json --output outputs/bouquet_crowns_v4/row_clearance_selected.json
& 'C:/Program Files/Blender Foundation/Blender 5.1/blender.exe' -b -t 4 --python scripts/lod_dense_field.py -- --source outputs/gazebo/bouquet_v4_textured --output outputs/gazebo/bouquet_v4_textured_lod --ratio .2 --minimum 24
.venv-training/Scripts/python.exe scripts/prepare_bouquet_flight.py --field outputs/gazebo/bouquet_v4_textured_lod --clearance outputs/bouquet_crowns_v4/row_clearance_selected.json --visual outputs/gazebo/neo_photo_visual_v3 --output outputs/gazebo/bouquet_row_flight_v1
```

Dentro de WSL, desde la raíz del repositorio:

```sh
python3 scripts/capture_bouquet_ab.py outputs/gazebo/bouquet_row_flight_v1 --variant flat
python3 scripts/capture_bouquet_ab.py outputs/gazebo/bouquet_row_flight_v1 --variant textured
python3 scripts/capture_bouquet_ab.py outputs/gazebo/bouquet_row_flight_v1 --variant flat_pbr
python3 scripts/run_bouquet_flight.py outputs/gazebo/bouquet_row_flight_v1 --name technical --seconds 10
python3 scripts/run_bouquet_flight.py outputs/gazebo/bouquet_row_flight_v1
```

En Windows, el entorno de la app ya incluye ONNX Runtime:

```powershell
outputs/desktop/venv/Scripts/python.exe scripts/evaluate_bouquet_ab.py outputs/gazebo/bouquet_row_flight_v1
outputs/desktop/venv/Scripts/python.exe scripts/analyze_bouquet_flight.py outputs/gazebo/bouquet_row_flight_v1/flight
```

No lanzar el vuelo completo si la prueba técnica falla. Las intersecciones
internas ya documentadas de v4 siguen pendientes; separación de navegación
y validez física de la arquitectura vegetal son comprobaciones distintas.

## Optimización usada para el video completo

`batch_bouquet_visuals.py` concatena exactamente los triángulos, normales y UV
por material. Reduce 2.631 mallas visuales a 19, sin cambiar ninguna de las
3.039 colisiones de esa copia. Mantiene 107.159 registros geométricos de órganos.
Esta copia no proporciona segmentación de instancias; la escena anterior
individualizada sigue siendo la fuente de la prueba A/B.

Después, `prepare_bouquet_flight.py --conservative-axis-colliders` sustituye
los pequeños cilindros de cada eje principal por un cilindro envolvente.
Comprueba que contiene las esferas de extremo de todos los cilindros originales
y, por convexidad, sus volúmenes completos. No se elimina volumen ocupado.
Se vuelve a comprobar el recorrido contra esas envolventes ampliadas. Los
tutores, cuerdas y marcadores no se cambian. Esta representación conservadora
reduce el coste de física; no valida fuerzas de contacto de un cosechador.

La ejecución completa está bajo `outputs/gazebo/bouquet_row_flight_batched_v2/`.
Las capturas A/B individualizadas están bajo `outputs/gazebo/bouquet_row_flight_v1/`.

```powershell
.venv-training/Scripts/python.exe scripts/batch_bouquet_visuals.py --source outputs/gazebo/bouquet_v4_textured_lod --output outputs/gazebo/bouquet_v4_textured_batched
.venv-training/Scripts/python.exe scripts/prepare_bouquet_flight.py --field outputs/gazebo/bouquet_v4_textured_batched --clearance outputs/bouquet_crowns_v4/row_clearance_selected.json --visual outputs/gazebo/neo_photo_visual_v3 --output outputs/gazebo/bouquet_row_flight_batched_v2 --conservative-axis-colliders
```

Ejecutar la prueba técnica y el vuelo con `run_bouquet_flight.py` sobre este
último paquete. Después, `compose_bouquet_video.py` genera el resumen a 4× y
verifica los tres videos con FFmpeg. `analyze_bouquet_flight.py` analiza las
muestras RGB originales con el modelo congelado. `report_bouquet_results.py`
reúne métricas A/B, telemetría, CSV de pasadas, mapa y reporte en español.
Usar directorios nuevos para repetir una ejecución; los existentes no se borran.
