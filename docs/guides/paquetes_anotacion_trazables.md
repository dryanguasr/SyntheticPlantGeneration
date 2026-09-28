# Cinco paquetes trazables de revisión

Esta entrega aplica el encargo del 25 de septiembre de 2026: regenerar un banco
de unas 4.500 imágenes reales para cinco estudiantes. El banco es material de
revisión, no una orden de segmentarlo todo ni un dataset aprobado para entrenar.
Paquete P01–P05 y partición train/val/test son conceptos independientes.

## Reglas vigentes

Segmentar instancias del **capacho visible de la planta/rama de trabajo en primer
plano**. Conservar oclusiones y truncamientos inequívocos; excluir hojas, tallos,
pedúnculos y partes ocultas. Derivar cajas después de las máscaras. No hay un
mínimo universal de píxeles: prevalece identificar la instancia y su contorno.

| ID | Clase | Estados del agricultor |
|---|---|---|
| 0 | pintona | 0–2 |
| 1 | madura | 3–4 |
| 2 | sobremadura | 5–6 |

Este contrato real de tres clases es propio de esta campaña. **No modifica** el
contrato histórico monoclase ni el experimento sintético de cuatro clases. Los
IDs no son los grados del agricultor. El color del capacho no valida la madurez
real del fruto; la herramienta no asigna clases ni infiere madurez.

Cada estudiante edita únicamente `seleccion.csv` (`image_id,decision`): USAR,
NO USAR, DUDOSA o vacío pendiente. La geometría ya anotada se conserva aunque la
imagen pase a DUDOSA. USAR no certifica anotación completa; la ausencia de
etiquetas no prueba que una imagen sea negativa.

## Entrada y formación del banco

La carpeta original es `Nuevo Dataset`. La entrega reducida v6 conserva el
manifiesto y **todos los candidatos del caché anterior**, además de sus 488
representantes. La herramienta lee el manifiesto completo y verifica los hashes
actuales de las fuentes y de cada candidato entregado. No restringe el banco a
los representantes de v6. No mezcla `Dataset Original`.

Se conservan todas las fotografías y se distribuye el presupuesto restante de
frames por cobertura temporal de los videos; se toman posiciones próximas a
tiempos uniformes usando los tiempos reales del decodificador registrados.
La semilla solo resuelve empates de presupuesto. No se calculan tiempos desde
FPS, no se usa detector, nitidez, color o similitud para excluir candidatos.
El presupuesto determina el **banco para revisión**, no cuotas finales de
selección o de etiquetado. `bank_selection.csv` registra el destino de todos los
candidatos padre; los que quedan fuera permanecen en el padre.

Los IDs heredados identifican fuente e índice secuencial de frame. Se registran
hashes de fuente, candidato, entrega y previsualización. Si cambia la fuente o
falta el caché, la ejecución se detiene; debe recuperarse explícitamente desde
el original antes de generar otra versión. No se inventan índices ni tiempos.

Las exclusiones históricas se entregan como NO USAR, con su antecedente técnico;
las reservas/representantes históricos no se convierten en aprobación humana.
Las fotografías orientadas y los frames son copias independientes del caché.
Las vistas PNG 640 usan INTER_LINEAR, proporción conservada y gris RGB114
centrado. Se registran escala efectiva por eje (redondeo a píxeles) y márgenes.
La vista y el original tienen **una sola identidad**.

## Reparto, calibración y particiones

Se asignan grupos completos cuando caben en una carga aproximada de un quinto.
Los grupos mayores se dividen en bloques de revisión ordenados por fuente y
frame; todos los bloques conservan group_id y split. Cada candidato tiene un
solo responsable principal. `groups.csv` registra propietarios y bloques.

Los cinco originales de `calibracion/` se copian en cada paquete con el mismo
ID, sin añadir filas de candidatos ni nuevas muestras. El coordinador adjudica
una sola anotación final por imagen. `piloto_sugerido.csv` propone hasta 40
imágenes únicas de train (incluidas las cinco) y diez de val, por grupos
distintos. Son propuestas automáticas por diversidad de grupos, pendientes de
revisión visual, no garantía de clases/escala ni cuotas de trabajo.

Revisión cruzada: primeras 5–10 por persona, después alrededor del 10 % de cada
lote y todas las DUDOSAS. Test no participa en calibración, entrenamiento,
autolabeling ni selección iterativa por errores; está marcado como reservado.

Se heredan los grupos y splits, incluidas relaciones conocidas entre dispositivos
y duplicados exactos. La auditoría comprueba grupos, fuentes, hashes y relaciones
del **pool padre completo**, incluso cuando un extremo no queda en el banco.
Un conflicto no se arregla repartiendo al azar: bloquea una futura liberación.
Los grupos pendientes también la bloquean. Hashes sin cruces no demuestran
independencia visual de plantas o recorridos. Futuras capturas deben relacionarse
con estos grupos antes de asignar split; fecha/archivo distinto no prueba
independencia. Tras entrenar no trasladar ejemplos de train a test para simularla.

## Comandos

Desde la raíz, con las dependencias ya existentes:

```powershell
.venv-training/Scripts/python.exe scripts/prepare_annotation_packages.py diagnose --output outputs/annotation_packages/captura_20260925_v1 --target 4500 --seed 20260925
.venv-training/Scripts/python.exe scripts/prepare_annotation_packages.py generate --output outputs/annotation_packages/captura_20260925_v1 --target 4500 --seed 20260925 --guide C:/Users/User/Downloads/Guia_seleccion_etiquetado_uchuva_4pag.pdf
.venv-training/Scripts/python.exe scripts/prepare_annotation_packages.py verify --output outputs/annotation_packages/captura_20260925_v1
.venv-training/Scripts/python.exe scripts/prepare_annotation_packages.py portability --output outputs/annotation_packages/captura_20260925_v1
.venv-training/Scripts/python.exe -m unittest discover -s tests -p test_annotation_packages.py
```

Diagnóstico no escribe paquetes. Generación rechaza destinos existentes: para
reproducir cambiar el sufijo a una versión nueva. No se reanuda parcialmente ni
sobrescribe una entrega. Los ZIP usan ZIP64 cuando hace falta y contienen archivos
reales, sin enlaces. Se comprueban todos sus bytes y enlaces internos de galería;
se extraen fuera del proyecto los cinco ZIP completos para comprobar portabilidad.
Las páginas estáticas cargan como máximo 40 miniaturas por página.

`portability` comprueba únicamente concordancia de CSV y extracción completa de
ZIP, registra sus SHA-256 en `verification_portability.json` y complementa una
auditoría existente de píxeles/hashes. No la sustituye. En esta entrega se
ejecutan ambas comprobaciones; una futura ejecución de `verify` también
incluye la extracción completa.

## Reunir devoluciones sin perder trabajo

El estudiante devuelve la exportación original de su editor y `seleccion.csv`.
El coordinador conserva ambas sin tocar en una carpeta de recepción por persona.
No debe pedir a estudiantes editar JSON técnico. El validador conserva una copia
de **todo** el árbol de recepción; la importación se ejecuta a una versión nueva:

```powershell
.venv-training/Scripts/python.exe scripts/prepare_annotation_packages.py import --campaign outputs/annotation_packages/captura_20260925_v1 --incoming outputs/devoluciones/ronda01 --output outputs/devoluciones_consolidadas/ronda01
```

El contrato técnico normalizado de importación es JSON. Un adaptador específico
del editor debe generar este JSON conservando también su exportación original;
no se afirma compatibilidad automática con exportaciones arbitrarias de SAM,
Ultralytics, YOLO o COCO. Cualquier formato no interpretado permanece en `raw/`.
No se eliminan instancias para acomodar un formato: se requiere un adaptador
explícito y revisión si el editor solo entrega RLE comprimido u otra estructura.

```json
{
  "classes": {"0": "pintona", "1": "madura", "2": "sobremadura"},
  "images": [{
    "image_id": "ID_DEL_MANIFIESTO",
    "filename": "ID_DEL_MANIFIESTO.jpg",
    "dimensions": [1920, 1080],
    "image_sha256": "HASH_DE_LA_REPRESENTACION_DEL_MANIFIESTO",
    "representation": "original",
    "annotation_complete": false,
    "instances": [{
      "class_id": null,
      "segmentation": [[12, 20, 30, 20, 30, 45]]
    }]
  }]
}
```

`representation` exige `original` o `640`, dimensiones y hash coincidentes.
`segmentation` admite polígonos múltiples o RLE COCO **sin compresión**, con
`size:[alto,ancho]` y `counts` completos, conservando huecos y componentes. La
geometría queda **sin transformar** en su sistema declarado; se adjunta la
transformación inversa para una futura conversión única. Para coordenadas 640:
`x_original=(x_640-left)/scale_x`, `y_original=(y_640-top)/scale_y`.
No aplicar esta operación otra vez a coordenadas originales.

Madurez desconocida se conserva como `class_id:null`, con revisión pendiente.
`decision` se obtiene del CSV; si también viene en JSON y contradice al CSV, la
imagen pasa a conciliación DUDOSA sin perder ninguna devolución. Los nombres
renombrados necesitan `filename_to_image_id` explícito y hash/dimensiones
coincidentes: nunca quitar sufijos ni asociar por orden o semejanza. Una imagen
recompuesta con bytes diferentes requiere conciliación externa documentada.
La partición devuelta por el editor no prevalece sobre el maestro.

Dos devoluciones de una misma imagen conservan ambas geometrías y requieren
adjudicación: nunca se sobrescriben ni se multiplican las muestras por revisor.
Las selecciones sin anotación también se conservan. El informe detecta clases
incompatibles (ID0 monoclase no equivale a pintona), máscaras mal formadas y
faltas de identidad. Ausencia de instancias nunca certifica negativos.

Este validador es un **ingreso de trabajo pendiente**, no un exportador de rondas
listas para entrenar: `training_release_allowed` permanece falso. La futura
liberación exige resolver errores, adjudicar, revisar exhaustividad y madurez,
validar grupos/relaciones y congelar el contrato. Esto evita presentar integridad
de archivos como validación científica o humana.
