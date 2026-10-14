# Piloto local de reconstrucción de uchuva

Este módulo observa geometría de una captura real. No redefine la arquitectura
botánica de `uchuva_lsystem`, ni promueve la reconstrucción a verdad de terreno.
Las salidas grandes permanecen en `outputs/reconstruction/`, ya ignorado por Git.

El piloto del 1 de octubre tiene un máximo de dos horas, incluyendo preparación,
intentos fallidos y cierre. La corrida principal del adjunto, de hasta ocho horas,
queda para una solicitud posterior. No se programa ni inicia automáticamente.
Configuración: `configs/reconstruction_pilot_20261001.json`.
Resultados: [informe del piloto](../reports/piloto_reconstruccion_uchuva_2026-10-01.md).

No reutilizar la fecha límite absoluta de esa configuración para mañana:
crear una configuración con su propio presupuesto y un directorio nuevo.

## Entrada y selección

El nombre exacto del adjunto no existe bajo `Nuevo Dataset`. El usuario confirmó
expresamente el archivo terminado en `video_beautify-006.mp4`. Su ruta relativa,
hash SHA-256, tamaño, metadatos y autorización constan en el manifiesto local.
El original se abre solo para lectura. No se presupone que el sufijo `beautify`
demuestre una edición ni que la focal permanezca constante.

```powershell
.venv-training/Scripts/python.exe scripts/inspect_reconstruction_video.py --config configs/reconstruction_pilot_20261001.json --output outputs/reconstruction/otra_inspeccion
```

La inspección inicial contiene 32 muestras distribuidas. La selección posterior
sondea cada segundo, pero conserva imágenes por desplazamiento de puntos seguidos
con flujo óptico y comprobación de ida/vuelta. Rechaza redundancia y difiere
imágenes borrosas; conserva imágenes de conexión al perder seguimiento o alcanzar
cuatro segundos sin una vista aceptada. Estos son criterios de ingeniería,
no evidencia automática de una trayectoria válida. Todos los candidatos y sus
decisiones quedan en `selection.json`, junto con índices y tiempos del decodificador.

```powershell
.venv-training/Scripts/python.exe scripts/prepare_reconstruction_frames.py --manifest outputs/reconstruction/pilot_20261001/input_manifest.json --output outputs/reconstruction/otra_seleccion --start 32 --end 360 --step 1 --long-side 960
```

El destino debe ser nuevo. No hay un holdout independiente en esta selección
exploratoria. No se calculan PSNR/SSIM/LPIPS sobre vistas usadas para reconstruir.
Para el principal se deberá fijar una partición de evaluación con separación
visual suficiente, después de identificar la misma región en ambos lados.

## Límites de ejecución

`scripts/run_reconstruction_stage.py` registra comando, tiempo de pared y RSS
agregada de procesos hijos cada segundo, y termina su grupo al salir. Recibe una
fecha límite Unix común a todos los intentos; un reinicio de etapa no la amplía.
El muestreo RSS puede contar páginas compartidas varias veces y omitir picos
subsegundo. En WSL se complementa con un servicio transitorio de systemd:
`MemoryMax=10G`, `MemorySwapMax=0`, `RuntimeMaxSec` acotado y sin concurrencia de
reconstrucciones. Es un límite inferior a la RAM de WSL observada, unos 15 GiB.
Definir también `WorkingDirectory` del servicio: systemd no hereda el directorio
de trabajo del shell invocante. La prueba del supervisor ejecutada terminó un
proceso `sleep 20` al agotar dos segundos y registró el estado `deadline`.
No se modifica el swap global ni se usa como ampliación de memoria del trabajo.

La GPU consultada es NVIDIA RTX 4050 Laptop, 6141 MiB. Gazebo Harmonic 8.14.0,
FFmpeg 6.1.1 y ROS Jazzy están presentes en Ubuntu 24.04/WSL. La disponibilidad
del ejecutable no certifica renderizado, física ni importación de esta captura.

## Dependencias y evidencia

OpenCV, NumPy, Pillow y psutil ya existen en el entorno Windows del proyecto;
WSL contiene OpenCV, NumPy, SciPy y psutil. No se modifican esos entornos.
La instalación de nuevas dependencias exige autorización explícita conforme a
`AGENTS.md`, y debe quedar aislada. La documentación de
[PyCOLMAP](https://colmap.github.io/pycolmap/index.html) ofrece ruedas CUDA para
Linux. Verificar capacidades y opciones de la versión efectivamente instalada.
[Nerfstudio](https://docs.nerf.studio/quickstart/installation.html) requiere una
preparación distinta; su disponibilidad no se infiere de tener PyTorch en Windows.

El usuario autorizó PyCOLMAP en este piloto. Se instaló `pycolmap-cuda12==4.2.1`
en `.venv-reconstruction-wsl`, con acceso de lectura a paquetes del sistema
(`--system-site-packages`) y bibliotecas CUDA locales al entorno. No se instalaron
controladores ni paquetes globales. COLMAP declara BSD-3-Clause; las bibliotecas
NVIDIA conservan sus licencias propias. El manifiesto `requirements_wsl.txt`
registra las cuatro distribuciones añadidas. No distribuir el entorno como si
estuviera cubierto por el MIT del código original del repositorio.

## Ejecutar las etapas de reconstrucción

Los comandos siguientes se ejecutan desde la raíz en Ubuntu/WSL. Cada destino
debe ser nuevo. En trabajo real envolverlos con el supervisor y el servicio
transitorio descritos arriba; no ejecutar un proceso sin plazo por copiar solo
el comando interno.

```bash
.venv-reconstruction-wsl/bin/python scripts/reconstruct_uchuva_sfm.py --selection outputs/reconstruction/pilot_20261001/selection_local --output outputs/reconstruction/mi_sfm --max-features 6000
.venv-reconstruction-wsl/bin/python scripts/reconstruct_uchuva_mvs.py --model outputs/reconstruction/mi_sfm/sparse/1 --images outputs/reconstruction/pilot_20261001/selection_local/images --output outputs/reconstruction/mi_mvs --views 16 --size 640
```

El número `1` es el componente útil de **esta** ejecución; seleccionar el modelo
de cada nueva corrida después de revisar su reporte. El componente `0` de este
piloto fue degenerado y se conserva como resultado negativo. No unir componentes
por parecido visual. `sfm_report.json` incluye cámaras, poses, puntos, reproyección,
opciones y tiempos; las cámaras y nubes también quedan en formatos COLMAP y PLY.

MVS usa una copia del componente reducida a las vistas exportadas. Pasar solo
`image_names` al rectificador no reduce las posibles fuentes del modelo, lo que
causó el primer fallo guardado. En PyCOLMAP 4.2.1, `stereo_fusion(output_type="ply")`
escribe PLY; `txt` significa una reconstrucción COLMAP en un directorio, no PLY
ASCII. La opción `--fuse-only` recupera mapas completos tras un fallo de escritura.
Ambas correcciones están verificadas con ejecuciones locales. API y semántica:
[PyCOLMAP](https://colmap.github.io/pycolmap/pycolmap.html),
[implementación de fusión](https://github.com/colmap/colmap/blob/main/src/colmap/exe/mvs.cc).

## Recorte e importación

`crop_reconstruction_foreground.py` proyecta la nube mediante la cámara recuperada
y selecciona un rectángulo y un intervalo explícito de profundidad. Guarda la nube
analítica, la imagen de evidencia y la transformación. No segmenta una planta
completa ni estima el plano del suelo. Revisar siempre su imagen antes de exportar.

`export_reconstruction_gazebo.py` reutiliza el ensamblador SDF del proyecto.
La nube se visualiza mediante pequeños parches orientados por sus normales,
con colores discretizados en materiales. **No hay una superficie continua ni una
malla cerrada reconstruida.** El radio de los parches es una heurística visual,
no un tamaño de órgano. La caja de colisión independiente rellena todos los huecos
de la copa y solo sirve para comprobar integración física.

```bash
python3 scripts/check_gazebo_field.py outputs/reconstruction/pilot_20261001/gazebo/field.sdf --timeout 100
python3 scripts/check_reconstruction_contacts.py outputs/reconstruction/pilot_20261001/gazebo --output-name nueva_prueba_contacto
```

El primer script recibe RGB por Gazebo Transport. El segundo guarda poses y
mensajes de contacto, comprueba apoyo de una esfera sobre la caja y caída de otra
por una columna exterior libre. Harmonic publicó los contactos en el tópico
jerárquico indicado por el log, no en el `<topic>` genérico del sensor; el primer
intento con la suscripción incorrecta permanece como fallo instrumentado.
Ni estas pruebas ni sus tolerancias numéricas validan un vuelo real.

El mundo usa una unidad de reconstrucción por metro SDF **solo para visualizar**.
No hay escala física del cultivo; tampoco se ha medido orientación gravitatoria.
La nube completa y el recorte conservan coordenadas originales por separado.

Separar poses/nube dispersa, MVS, malla de superficie, visual simplificada y
colisión. Un archivo de gaussianas no es una superficie medible. La carga SDF
estática tampoco prueba una cámara real de Gazebo ni contacto físico.

Sin un par de postes identificado y verificable, conservar unidades arbitrarias.
Si se identifica una distancia reconstruida `d`, el intervalo provisional de
escala será `[3.15/d, 3.50/d]`; no es un intervalo de confianza. No inferir altura
física, biomasa ni área foliar total de una nube incompleta.

## Continuación: superficie observada y textura fotográfica

El primer cierre a los 64 minutos fue prematuro. La continuación conserva sus
artefactos y usa `outputs/reconstruction/pilot_20261001_improved/`. Aumenta MVS
a 51 vistas y 1280 píxeles, manteniendo la calibración del componente local.
El mismo recorte permite comparar muestreo sin confundirlo con exactitud física.

`mesh_reconstruction_surface.py` aplica Poisson, conserva la malla cruda y
descarta caras alejadas de la nube observada o con aristas excesivas. Los umbrales
son heurísticas en unidades arbitrarias, no tolerancias botánicas. Asigna a cada
triángulo una foto cuya profundidad MVS concuerde con su centro; conserva por
separado los triángulos sin textura admisible. Las normales explícitas del OBJ
son necesarias para que esta exportación muestre las texturas en Gazebo Harmonic.

Ejemplo en el entorno WSL autorizado, con las mismas salvaguardas de tiempo/RAM:

```bash
.venv-reconstruction-wsl/bin/python scripts/mesh_reconstruction_surface.py \
  --crop outputs/reconstruction/pilot_20261001_improved/foreground \
  --mvs outputs/reconstruction/pilot_20261001_improved/mvs \
  --output outputs/reconstruction/nueva_superficie \
  --depth 10 --trim 5 --support-distance .045 --max-edge .15
```

La salida incluye `poisson_raw.ply`, `supported_surface.npz`, `surface_report.json`
y un paquete `gazebo/` con OBJ, MTL y fotografías copiadas localmente. Las fotos
contienen contexto del cultivo; no se publican. La malla es una interpolación
parcial respaldada por observaciones, no una segmentación de órganos ni una
superficie vegetal cerrada certificada. La colisión sigue siendo una caja aparte.

`evaluate_reconstruction_density.py` compara espaciado de muestras y distancias
bidireccionales entre nubes que ya comparten poses/coordenadas. No realiza una
alineación automática ni calcula exactitud contra verdad de referencia.
`package_reconstruction_blender.py`, ejecutado mediante Blender, guarda una
escena con texturas empacadas y GLB para inspección; conserva la advertencia de
escala arbitraria. No convierte la malla visual en datos morfológicos verdaderos.

El intento de recuperar imágenes del regreso permite fijar los cuatro parámetros
SIMPLE_RADIAL con `reconstruct_uchuva_sfm.py --fixed-intrinsics f cx cy k`.
Solo es válido para imágenes de la misma resolución y cámara; la procedencia
de esa estimación debe constar en el informe. No basta el número de cámaras para
aceptar ambos lados: revisar referencias estáticas, trayectoria y conexiones.

Para recortes más grandes, `mesh_reconstruction_surface.py --auto-frame` adapta
las cámaras a la caja observada. `align_reconstruction_cameras.py` conserva la
similitud y los residuos de las cámaras comunes; no valida identidad de planta.
`simplify_reconstruction_blender.py` reduce solo la representación visual y
conserva las texturas. Su diagnóstico interno es por grupo de cámara; para
valorar toda la malla deben consultarse además las distancias globales guardadas
en el piloto. Incluso una variante visualmente similar puede perder fragmentos.
