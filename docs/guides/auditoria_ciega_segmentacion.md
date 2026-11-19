# Auditoría ciega de segmentación

Abrir con doble clic `scripts/abrir_auditoria_segmentacion.cmd` desde el
Explorador de archivos. Usa el Python y las dependencias ya presentes en el
proyecto; no instala nada y no requiere HTML ni navegador.

El piloto está en `outputs/blind_segmentation_50_20261113`: 50 imágenes
exclusivamente de entrenamiento, 30 aleatorias y 20 difíciles. Se excluyen
las imágenes usadas en pruebas técnicas y los grupos de validación/test.

1. Indicar el nombre o identificador en el diálogo de perfil de la primera
   apertura y segmentar las instancias visibles. El perfil se recuerda y se
   puede editar desde la barra superior. En polígono, cada clic añade un
   vértice y Enter lo cierra. La rueda amplía y el botón derecho mueve la vista.
2. Usar pincel/borrador para retocar. «+ Parte» y «- Hueco» conservan regiones
   desconectadas y oclusiones de una misma instancia. «No resoluble» expresa
   incertidumbre en el registro de revisión; no añade una clase de entrenamiento.
3. Guardar borrador para continuar después. La propuesta sigue oculta.
4. «Guardar y comparar» congela la primera anotación manual
   y revela propuesta y original. Las cajas se derivan de los píxeles de la
   máscara; su visualización es opcional y está desactivada por defecto.
5. Si procede, editar una copia y guardar una adjudicación separada. La primera
   versión manual y las etiquetas originales no se sobrescriben.
6. Exportar la auditoría. Sólo incluye imágenes cuyo manual ya se confirmó;
   conserva máscaras RLE nativas, clases, cajas derivadas, notas y versiones.

Los trabajos se guardan en `audits/principal` dentro del piloto. «No hay
instancias» requiere confirmación explícita si se guarda una imagen vacía.
No se exportan cambios automáticamente al dataset ni se inicia entrenamiento.

Las propuestas son máscaras **provisionales** generadas con localizadores
existentes y GrabCut sobre RGB. No son segmentaciones validadas ni propuestas
de un nuevo modelo entrenado. Los localizadores vieron train durante su
entrenamiento: esta auditoría no mide generalización sobre datos nuevos.
Los polígonos originales de NDJSON se preservan íntegros por separado.

La revisión visual inicial se interrumpió cuando el usuario detuvo Computer
Use. El 19/11 se comprobó el diseño renovado en una demostración separada:
atajo S, escritura protegida, foto encajada, lupa y controles de guardado.
Hay pruebas de máscaras, guardado, bloqueo de propuestas, inmutabilidad y
comparación; eso no sustituye la auditoría humana de las 50 fotos.
Generación y piloto de aumentación permanecen pausados.

## Lupa y escala de referencia (19/11/2026)

La **lupa permanece abierta**, en la esquina superior derecha, sin botón de
cierre. Mover el cursor sobre cualquiera de las imágenes muestra su RGB
original ampliado, sin rellenos de segmentación. Hay aumentos 2×, 4×, 8× y 12×,
lectura del píxel y mediana local 5×5; «Fijar» mantiene el último punto. Al
cambiar de imagen se limpia la muestra para no confundir referencias.

Justo bajo el borde inferior del recorte ampliado hay una sola fila de colores
del **capacho**. Debajo de cada color aparece su grado y, debajo del número,
su clase empírica. La referencia contiene siete grados (0–6), que se conservan
íntegros para contrastar la ROI al mover el cursor. Cada muestra es la mediana por canal dentro de una
región circular explícita, con coordenadas, radio, RGB, hexadecimal y hash de
origen en `docs/references/annotation_norma_palette.json`. Pulsar una muestra
revela sus valores; «Ver lámina y zonas muestreadas» abre la referencia con
las regiones del capacho marcadas. El manifiesto conserva también el muestreo
histórico del fruto como procedencia, pero no se muestra en la escala de la lupa.

La agrupación histórica acordada del piloto disperso es 0–1 verde, 2–4
pintona, 5 madura y 6 sobremadura. Es una aproximación visual documentada en
`sparse_pilot.class_for_grade`, no una nueva clase para este dataset ni una
interpretación normativa validada. La ilustración no representa todos los
grados de deterioro ni ofrece colorimetría calibrada. La lupa no asigna clases.

Esta ayuda puede consultarse antes del manual, pero no revela anotaciones ni
propuestas de la imagen. Los nuevos borradores/manuales registran la versión
de herramienta y la procedencia de referencia utilizada. Las versiones
manuales ya guardadas permanecen intactas. La revisión de la aplicación se
archiva por separado y conserva todos los hashes de datos/propuestas.

## Segmentación asistida por clics y nodos (19/11/2026)

La opción **SAM · clic + / Shift clic −** usa MobileSAM local con el
Ultralytics ya instalado. No envía fotos a un servicio ni utiliza los
localizadores, propuestas o etiquetas originales de la imagen. El modelo
segmenta la región indicada; **la clase la elige la persona**.

1. Selecciona SAM y haz clic dentro del capacho. Añade puntos interiores si
   hace falta; **Shift+clic** marca fondo o zonas que deben excluirse.
   Ctrl+Z quita el último punto. La interfaz calcula en segundo plano y
   reutiliza el codificador de imagen para los siguientes clics de esa foto.
2. Revisa la máscara provisional azul. **Aceptar máscara SAM** crea una
   instancia nueva; **Descartar puntos / máscara** o Escape la descarta.
   Antes de aceptar, no forma parte de las anotaciones. Para guardar o cambiar
   de imagen hay que aceptar o descartar la vista previa pendiente.
3. Tras aceptar se activa **Nodos del borde**. Selecciona una máscara y usa:
   **Mover**, arrastrando un cuadrado blanco; **Insertar**, haciendo clic junto
   a un segmento del borde; o **Eliminar**, haciendo clic sobre un nodo.
   En este modo **Shift+clic** junto al borde inserta y **Ctrl+clic** sobre
   un nodo elimina, sin cambiar el selector. Insertar sólo divide el segmento:
   la máscara no cambia hasta moverlo. **Ctrl+Z** deshace cada operación.
   El contorno debe conservar al menos tres nodos y no puede cruzarse consigo
   mismo. Los nodos añadidos se conservan en el borrador junto con el hash de
   su máscara; no se pierden al reabrirla. También puedes editar una máscara
   manual. Pincel, borrador, partes y huecos siguen disponibles.
4. **Nueva instancia** inicia otro capacho; si SAM sigue seleccionado basta
   marcar el siguiente. La lupa permanece abierta para decidir la clase.

El selector `auto` usa GPU CUDA si está disponible y CPU en caso contrario;
`cpu` permite trabajar sin ocupar GPU. **Elegir pesos SAM…** permite usar
archivos locales compatibles MobileSAM, SAM o SAM2 con sus nombres oficiales.
No descarga pesos automáticamente ni instala paquetes al abrir la aplicación.
Los pesos MobileSAM por defecto están en `outputs/annotation_assistance_models`,
con SHA256 y URL original documentados en
`docs/references/annotation_assistance_model.json`. Conservan sus términos de
terceros, al igual que Ultralytics; el MIT del repositorio no los relicencia.

La máscara se conserva como RLE a resolución nativa, incluidos partes y huecos;
las cajas se derivan de sus píxeles. Los nodos son una aproximación del borde
para editar, no un reemplazo automático de la máscara: activar la herramienta
no cambia píxeles. Mover o eliminar un nodo aplica sólo la diferencia local del contorno;
el resto de la máscara se conserva. Las máscaras SAM requieren revisión,
especialmente con órganos pequeños, superpuestos o translúcidos.

Este uso cambia la primera anotación de «manual sin modelo» a **anotación
asistida por modelo y guiada por la persona**, aunque sigue ciega respecto a
las propuestas anteriores. Se registra `annotation_method`, más pesos/hash,
versión, clics positivos/negativos y edición de borde por instancia. Hay que
separar ambos métodos al analizar el acuerdo o el tiempo de auditoría; no
presentar el acuerdo posterior como una validación humana independiente sin
ayuda. Las primeras versiones ya guardadas y originales permanecen intactas.
La generación y el piloto de aumentación continúan pausados.

Contrato técnico contrastado con la [documentación oficial de SAM en
Ultralytics](https://docs.ultralytics.com/models/sam/) y con el código local
de la versión 8.4.114; no se actualizó el entorno.

## Barra inferior y atajos por contexto

La barra inferior reserva su propio espacio y muestra, con texto de alto
contraste, el modo activo y sus comandos. Los botones de herramientas incluyen
sus teclas y resaltan el modo seleccionado. La ayuda cambia entre polígono,
SAM pendiente/listo, nodos, pincel/borrador y comparación de sólo lectura.

| Tecla | Acción |
|---|---|
| P | Polígono |
| S | SAM por puntos |
| V | Seleccionar instancia |
| B / E | Pincel / borrador |
| M / I / D | Mover / insertar / eliminar nodos |
| N | Nueva instancia |
| F | Encajar imagen |
| Enter | Cerrar polígono o aceptar una máscara SAM lista, según el modo |
| Esc | Cancelar el contorno o descartar puntos/máscara provisional |
| Ctrl+Z | Deshacer; en SAM quita el último punto |
| Ctrl+S | Guardar borrador o adjudicación editable, según la fase |
| Alt+← / Alt+→ | Imagen anterior / siguiente, con las guardias de guardado |
| 1 / 2 / 3 / 4 | Pintona / Madura / Sobremadura / No resoluble |
| Supr | Eliminar la **instancia completa**, no un nodo |

En nodos siguen funcionando Shift+clic para insertar y Ctrl+clic para eliminar.
Rueda amplía y botón derecho mueve la vista. Las herramientas de edición no
operan sobre originales, propuestas o primeras versiones congeladas. Mientras
el foco está en notas, nombre o selectores, los atajos de edición se suspenden
para permitir escribir y usar las teclas propias del campo; Ctrl+S conserva su
función de guardar. Haz clic en la imagen o en un botón de herramienta para
retomar los atajos. El cambio de herramienta mantiene la conducta anterior:
descarta el contorno o la máscara provisional que todavía no se haya aceptado.

## Diseño de la aplicación y teclado Windows (19/11/2026)

La interfaz **Uchuva / Annotation Lab** reúne los desplegables de imagen,
instancia y clase en la barra superior junto con **Perfil…**. El lienzo ocupa
el espacio central y la lupa conserva su columna a la derecha. **Notas de
revisión** abre un editor compacto en la esquina inferior derecha. Al cerrarlo,
el texto sigue disponible para guardar el borrador o la adjudicación.

La barra inferior muestra los comandos y parámetros de la herramienta activa.
**Ayuda** abre una ventana independiente para cada herramienta con sus
instrucciones y atajos. **F1** abre la ayuda de la herramienta activa.

La app abre maximizada. **F11** o **Pantalla** oculta el marco de
la ventana y la barra de tareas. Pulsa **F11** de nuevo para volver a la
ventana. En pantallas bajas se compactan la cabecera y la lupa para dar más
altura al lienzo. Si una barra queda estrecha, los controles pasan a la
fila siguiente.

El lienzo se encaja al abrirse o cambiar de tamaño, conservando un zoom o
desplazamiento que la persona haya elegido. «Encajar» restablece el ajuste.
Las acciones de guardado tienen espacio reservado por encima de los comandos
inferiores.

Se corrigió el filtro de atajos: en Tk/Windows, `Mod1Mask` (`0x08`) representa
Bloq Num, mientras Alt usa otro indicador. El filtro anterior ignoraba S y
otras letras con Bloq Num activo. Ahora se distinguen Windows y X11 y se
mantienen las guardias de texto, Ctrl y Alt. La correspondencia se contrastó
con el [código oficial de Tk para Windows](https://github.com/tcltk/tk/blob/core-8-6-branch/win/tkWinX.c).

La captura de revisión es una **demostración**, con máscara provisional y
clase «No resoluble», no una muestra de anotación humana aprobada. La edición
de interfaz no modifica imágenes, máscaras originales, propuestas ni trabajo
humano guardado. No inicia generación ni entrenamiento.

## Ronda cruzada de seis personas

La ronda se prepara desde el piloto sellado de 50 fotografías con
`python scripts/prepare_cross_review.py prepare RUTA_NUEVA`. Se crean
**aplicacion**, **revisores/R01** a **revisores/R06** y **coordinacion**.
Entregar a cada persona sólo su carpeta R y la carpeta común **aplicacion**.
Asignar un código distinto a cada persona y guardar la correspondencia en
coordinación. La carpeta **coordinacion** contiene propuestas y entregas
importadas y se mantiene privada.

Cada lote incluye el [manual PDF para estudiantes](manual_estudiantes_revision_cruzada.pdf)
con capturas de la interfaz, pautas de anotación y el paso a paso de entrega.
Para preparar los archivos de una ronda existente, ejecutar:

```powershell
python scripts/prepare_cross_review.py distribute RUTA_RONDA RUTA_DISTRIBUCION_NUEVA
```

El comando genera `aplicacion.zip` y `R01.zip` a `R06.zip`. Cada ZIP R
contiene su propio lote, con las imágenes, los manifiestos sellados y el PDF.
Comparte `aplicacion.zip` y únicamente el ZIP asignado a cada estudiante por
el canal privado del curso. Para empezar, se extraen ambos ZIP en la misma
ubicación. Los borradores, las entregas y las propuestas de coordinación
quedan fuera de la distribución.

El repositorio versiona el código, el lanzador, los metadatos y el manual.
Para reconstruir los ZIP desde un clon, coordinación necesita la ronda
local sellada y dos archivos autorizados: `Nuevo Dataset/Norma.webp` (la
lámina original de donde se obtuvieron los colores) y
`outputs/annotation_assistance_models/mobile_sam.pt`. Consulta los hashes
en `docs/references/annotation_norma_palette.json` y
`docs/references/annotation_assistance_model.json`. Este último también
registra el enlace oficial para obtener los pesos.

En Windows, abrir `aplicacion/scripts/abrir_revision_cruzada.cmd` y elegir
la carpeta del lote. Usa el Python del proyecto en este equipo. En otro PC,
el lanzador usa `pythonw.exe` de PATH o el indicado por la variable
`UCHUVA_PYTHON`. El kit se verificó con Python 3.12. Ese Python debe disponer de Tk, Pillow, NumPy, OpenCV y
Ultralytics con PyTorch para SAM. El kit contiene la referencia de color
y los pesos locales de MobileSAM. Las bibliotecas Python se mantienen en
el entorno que ya utilice cada equipo.

1. Indicar el nombre en el perfil. El código del lote se mantiene fijo.
2. Anotar con las herramientas manuales o con SAM. Usa **Guardar borrador**
   o Ctrl+S para confirmar el guardado. La app guarda también tras ediciones
   cerradas. Un polígono abierto o puntos SAM pendientes se deben terminar
   o descartar antes de cambiar de imagen.
3. Pulsa **Entregar y seguir** cuando termines. La entrega queda en sólo
   lectura y la app pasa a la siguiente pendiente. Marca «Sin instancias»
   sólo cuando confirmes que la imagen no tiene instancias que anotar.
4. Pulsa **Exportar** y entrega a coordinación el ZIP indicado por la app,
   que contiene únicamente entregas confirmadas. Se puede enviar un ZIP
   acumulativo al completar más imágenes.

Coordinación abre `coordinacion/abrir_coordinacion.cmd` e importa los ZIP
mediante **Importar ZIP**. Cuando una imagen tiene dos
entregas, ambos paneles permiten seleccionar **Humana A**, **Humana B** o
**Piloto**. Los paneles comparten el zoom y el centro de la imagen. La vista
de diferencia muestra los píxeles presentes en una sola de las dos máscaras
emparejadas y las instancias sin pareja. Las diferencias de clase aparecen
en las notas de la comparación. **Registrar resolución** conserva el
criterio de coordinación como registro separado. **Exportar** genera el
informe de acuerdo de los casos con las dos entregas.

El informe cuenta coincidencias de máscara con IoU ≥ 0,5 y distingue el
acuerdo de clase entre instancias emparejadas, los casos no resolubles y las
instancias sin par. Desglosa cada pareja por dificultad y por exposición a
SAM (sin SAM, vista o aceptada). Las propuestas GrabCut del piloto se
conservan por huella. El informe describe concordancia en las fotografías
del lote, que provienen del conjunto de entrenamiento.

Antes de iniciar la ronda, hacer una práctica con imágenes fuera del lote
en cada equipo. La revisión automatizada de esta entrega se realizó
con ventanas ocultas, sin operar el escritorio.
