# Nuevo dataset real: extracción y entrega para etiquetado

## Contrato y límites

El conjunto es independiente de `Dataset Original`. Se preparan imágenes sin
etiquetas ni inferencia del detector, con objetivo train/val/test de 70/15/15 y
semilla 20260922. Una imagen sin etiquetar **no es un negativo**. No se crean
archivos YOLO vacíos ni se asignan clases o madurez a partir del color del capacho.
Una sola jornada no demuestra generalización a otras fechas o fincas.

La entrega inicial es **provisional**: la semejanza visual propone relaciones,
pero no demuestra independencia entre plantas o áreas. La ausencia de un par
perceptual no certifica ausencia de filtraciones. Los estudiantes deben revisar
grupos, orientación, calidad y escalas antes de congelar el conjunto y entrenar.

## Uso reproducible

Desde la raíz del repositorio, con el entorno existente que contiene OpenCV,
NumPy y Pillow (sin instalar dependencias):

```powershell
.venv-training/Scripts/python.exe scripts/prepare_new_real_dataset.py run --version captura_20260912_v1
.venv-training/Scripts/python.exe scripts/prepare_new_real_dataset.py verify --version captura_20260912_v1
```

La entrada por defecto es `Nuevo Dataset` y la salida es
`outputs/new_real_dataset/<version>`. Los originales permanecen intactos y fuera
de Git. El inventario incluye referencias no multimedia, hashes SHA-256,
dimensiones, EXIF disponible y metadatos de video. Un cambio de contenido,
nombre o archivos bloquea la reutilización de una versión. Los tiempos de
duración del inventario son estimaciones; cada candidato registra el índice
secuencial del frame y el tiempo del decodificador. No se utiliza FPS promedio
para localizar frames. Los errores de decodificación en fuentes seleccionadas
bloquean la congelación; los archivos ilegibles descartados permanecen en el informe.

Etapas disponibles: `inventory`, `candidates`, `review`, `partition`, `export`,
`verify`, `freeze`. `run` ejecuta hasta exportación/verificación. La extracción
interrumpida se reanuda por fuente completa; una entrega ya exportada no se
sobrescribe. Los candidatos y sus miniaturas son inmutables.

Los valores siguientes son **engineering_heuristic**, no hechos botánicos:
muestreo regular de un segundo; sondeo cada medio segundo; cambio medio RGB
de 18/255 para retener un sondeo intermedio; dHash a distancia máxima 4 más
diferencia media de miniaturas de hasta 12/255 y proporciones similares para
proponer duplicados; ráfagas fotográficas del mismo dispositivo separadas por
hasta 90 segundos para proponer grupos. Ninguno reemplaza la revisión humana.

La medida de cambio reduce la imagen con promedio de área para evitar que
texturas finas y pequeños movimientos produzcan cambios artificiales al reducir
resolución. Al reutilizar un caché sobremuestreado, los sondeos intermedios sin
cambio suficiente se mantienen en reserva, sin borrar sus archivos.

Las imágenes se proponen en orden de nitidez, reservando únicamente aquellas
con semejanza directa a un representante ya seleccionado. No se colapsan cadenas
transitivas que podrían borrar un zoom gradual. Las restantes permanecen en
**reserva**, accesibles a resolución completa. La nitidez no excluye imágenes ni demuestra que un capacho
sea identificable. No hay cupo por video ni tamaño final prefijado. Escenas
distintas, escalas raras y cambios útiles de perspectiva deben recuperarse de
la reserva si la similitud automática los agrupó indebidamente.

## Revisión de la entrega

Abrir `index.html`: enlaza a las galerías de candidatos, fuentes y pares similares.
Las miniaturas enlazan a cada candidato original; las rotaciones de revisión
se aplican a las imágenes exportadas sin alterar esos candidatos.
`images/train`, `images/val`, `images/test` contienen la propuesta para etiquetar;
`manifest.csv` y `manifest.jsonl` conservan procedencia, hash, frame/tiempo, grupo,
split y estado. `report.json` cuantifica la cobertura y sus pendientes;
`extraction_issues.json` registra archivos ilegibles y problemas de extracción.

Antes de editar las tablas de revisión, crear una versión nueva:

```powershell
.venv-training/Scripts/python.exe scripts/prepare_new_real_dataset.py fork-review --from-version captura_20260912_v1 --version captura_20260912_v2
```

Editar únicamente las tablas de la nueva versión. No editar candidatos ni
miniaturas: las versiones comparten sus bytes mediante enlaces duros. Las
imágenes entregadas para etiquetar son copias independientes.

- `source_review.csv`: asignar `group_id` común a todas las fuentes que muestran
  la misma planta/área o recorrido relacionado, incluso entre dispositivos.
  Mantener cada video entero en un grupo. Revisar secuencias fotográficas y
  referencias del lugar, no solo nombres/horarios. Usar `rotation_cw` de
  0/90/180/270 si la imagen decodificada aún está girada. Registrar evidencia en
  `notes` y marcar `group_review=reviewed` solo después de revisar.
- `pair_review.csv`: resolver `pending` como `duplicate`, `same_scene` o
  `different_scene`. Los pares pendientes permanecen juntos conservadoramente;
  las coincidencias exactas no pueden separarse mediante una edición.
  `same_source` registra el hecho de proceder del mismo video, ya indivisible;
  no afirma que sea la misma planta ni requiere decidir de nuevo su split.
- `image_review.csv`: `selection` admite `include`, `reserve`, `exclude`;
  documentar motivo para reservas/descartes. Revisar desenfoque, exposición,
  transiciones y utilidad; marcar `quality_review=reviewed`. No eliminar un
  plano solo porque contiene objetivos pequeños o tiene poca textura.
- Registrar presencia simultánea de `small`, `medium`, `large` con `yes/no`.
  Son escalas **visuales provisionales**, no categorías cuantitativas de cajas
  ni distancias físicas. Acordar ejemplos comunes entre estudiantes y registrar
  ese criterio antes de marcar `scale_review=reviewed`. Revisar a resolución
  completa. Usar `incierto=yes` cuando no sea posible distinguir, y
  `sin_objetivo_visible=yes` solo tras inspección; no equivale todavía a un
  negativo exhaustivamente etiquetado. El estado inicial es `unknown`.

Conservar identificadores, nombres y particiones durante el etiquetado. No
inferir madurez ni inventar cajas para puntos irreconocibles. La revisión de
escalas no es anotación completa de instancias. Tras etiquetar, medir también
tamaño de cajas a la resolución de entrada del detector para evaluar el problema
de objetos pequeños cuantitativamente.

Recalcular y exportar la versión revisada:

```powershell
.venv-training/Scripts/python.exe scripts/prepare_new_real_dataset.py partition --version captura_20260912_v2
.venv-training/Scripts/python.exe scripts/prepare_new_real_dataset.py export --version captura_20260912_v2
.venv-training/Scripts/python.exe scripts/prepare_new_real_dataset.py freeze --version captura_20260912_v2
```

La asignación agrupa todas las relaciones no descartadas y optimiza conteos
globales y de tipo/dispositivo mediante 128 órdenes reproducibles. Los grupos
prevalecen sobre el porcentaje. No se promete balance de escala mientras falte
la revisión; se informan imágenes **y grupos** por escala/split. Si falta una
escala, recuperar candidatos de los grupos correspondientes o documentar una
nueva captura. Nunca duplicar imágenes para aparentar cobertura. Un grupo por
escala/split es solo un requisito mínimo del bloqueo, no evidencia suficiente
de representatividad estadística.

`freeze` exige revisiones resueltas, tres splits no vacíos, presencia de las tres
escalas en cada split e integridad del paquete. Un problema real de extracción
requiere corregir la causa y extraer en una nueva versión, o excluir de la
selección toda la fuente afectada con justificación; no borrar el informe.
El sellado registra hashes; cambios posteriores requieren una nueva versión.
No entrenar mientras el estado sea provisional. Reservar test para evaluar un
modelo ya seleccionado usando train/val; no elegir imágenes según predicciones
del detector anterior.

Los conteos de escala son presencias **revisadas**, no estimaciones automáticas:
un cero acompañado de `scale_pending` no significa que falten capachos pequeños,
sino que todavía no se ha establecido esa cobertura.

## Integración futura

Si el tiempo lo permite, estudiar por separado la integración con el histórico,
con auditoría de coincidencias entre conjuntos y comparación por dominio/escala.
No mezclar ahora sus particiones ni convertir el test histórico, ya consultado,
en un supuesto holdout externo intacto.

## Validación de la herramienta

```powershell
.venv-training/Scripts/python.exe -m unittest discover -s tests -p test_dataset_curation.py
.venv-training/Scripts/python.exe scripts/validate_repository_context_graph.py
```

Las pruebas usan medios pequeños generados: orientación EXIF, recomprensión,
archivo corrupto, tiempos de video, cambios de origen, grupos completos,
determinismo e integridad del exportado. No sustituyen validación humana.


### Excluir contenido conservando la partición

En una nueva versión creada con `fork-review`, marcar `selection=exclude`
en `image_review.csv` y registrar el motivo en `notes`. La galería omite
los excluidos, pero los manifiestos mantienen su trazabilidad. Para conservar
la partición, crear `preserved_splits.json` con la propiedad `groups` copiada
de `split_assignment.json` de la versión anterior. La herramienta usa esa
asignación y falla si no cubre los grupos actuales. Este archivo se conserva
al crear versiones siguientes y su integridad se comprueba tras exportar.
Si cambia la agrupación, revisar explícitamente la política antes de volver
a particionar. No modificar una entrega ya exportada.


### Reducir redundancia temporal

`scripts/reduce_video_redundancy.py --parent outputs/new_real_dataset/captura_20260912_v3 --output tmp/video_redundancy.json` compara frames seleccionados del mismo video con hasta tres representantes recientes conservados. Requiere la copia `images_640x640` y su manifiesto. Usa ORB y un ajuste geométrico robusto; protege variaciones de escala aparente mayores al 15 %, cambios importantes de encuadre o iluminación y casos sin correspondencias suficientes. Los umbrales son heurísticas de ingeniería, no medidas de cobertura de capachos.

Cada reserva apunta directamente a una imagen conservada; no se descartan cadenas transitivas de escenas. Aplicar propuestas a una versión nueva como `selection=reserve`, conservando asignaciones de split y exclusiones previas. No marcar estas reservas como duplicados exactos. La galería principal muestra únicamente imágenes seleccionadas; el manifiesto mantiene candidatos recuperables. Fotografías y revisión de escalas siguen sujetas al protocolo original.


### Limitar el volumen para etiquetado

`scripts/select_dataset_budget.py --parent outputs/new_real_dataset/captura_20260912_v4 --output tmp/budget_2400.json --total 2400` propone una selección de 2400 imágenes sin mover imágenes entre splits. Conserva fotografías y al menos un frame de cada video representado; distribuye el presupuesto restante proporcionalmente a los frames previamente seleccionados por origen dentro de cada split. Selecciona mediante distancias de apariencia (disposición espacial Lab, bordes, color y una contribución temporal pequeña), comparando cada candidato contra la selección ya retenida. Las cuotas se introducen por el presupuesto solicitado, no como prueba de igual diversidad entre videos. Los descriptores son heurísticas y la cobertura de capachos pequeños sigue pendiente de revisión humana. Aplicar a otra versión y conservar los casos retirados como reservas recuperables.


### Selección visual v6

La entrega `captura_20260912_v6` contiene 488 representantes seleccionados visualmente, sin presupuesto fijo. Conserva los splits anteriores y las reservas recuperables. Consultar `visual_selection_review.json` para los identificadores exactos y las limitaciones de la revisión del asistente. Las escalas siguen pendientes: revisar objetos pequeños a resolución original antes de certificar cobertura. Las imágenes de `images_640x640/` son copias derivadas para entrada al modelo; `images/` conserva la resolución original de entrega.


### Copia derivada con relleno en espejo

Para conservar los originales y generar copias de 640 × 640 con relleno lateral e inferior en espejo y superior gris (114):

```powershell
.venv-training/Scripts/python.exe scripts/export_mirror_dataset.py --parent outputs/new_real_dataset/captura_20260912_v6 --output outputs/new_real_dataset/captura_20260912_v6_espejo --size 640
```

El destino debe ser nuevo. `originals/` conserva los bytes de los originales orientados; `images_640x640/` contiene PNG. Ambos preservan nombres y splits. Se mantiene proporción y se centra el contenido sin recortar. El espejo usa `BORDER_REFLECT_101`; la franja superior, si existe, permanece gris. El manifiesto registra escala, márgenes, grupos y hashes. El espejo puede repetir objetos: etiquetar sobre los originales y usar la transformación registrada para las coordenadas. Estas copias no implican cobertura nueva de escalas ni validación humana.
