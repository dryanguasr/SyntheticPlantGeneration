# Exportación CAD del robot con Inventor

`scripts/export_inventor_robot.ps1` interpreta copias locales IAM/IPT mediante
Inventor instalado. Exporta evidencia geométrica del diseño; no confirma que
las piezas, densidades, motores o montajes coincidan con el prototipo construido.
No convierte restricciones de ensamblaje en articulaciones del robot.

## Ejecución

Requiere Windows PowerShell 5.1 en STA, Inventor registrado y una licencia que
permita abrir los documentos. No instala dependencias. Cerrar primero las
sesiones propias de Inventor: el exportador se niega a reutilizarlas o cerrarlas.

```powershell
powershell.exe -NoProfile -STA -File scripts/export_inventor_robot.ps1 `
  -OutputDirectory outputs/real_harvester_cad/com_probe_nuevo -ProbeOnly

# Desde una sesión PowerShell: conservar nombres y subcarpetas de las referencias.
./scripts/export_inventor_robot.ps1 `
  -SourceRoot outputs/real_harvester_cad/source `
  -Assemblies @('gripper/Gripper ensamble.iam', 'arm/Ensamble brazo v2.iam') `
  -OutputDirectory outputs/real_harvester_cad/export_nuevo `
  -ChordToleranceM 0.0002

powershell.exe -NoProfile -STA -File tests/test_inventor_export_helpers.ps1
```

Las carpetas de salida deben ser nuevas y exteriores a las copias CAD. Los
documentos se abren invisibles, se cierran con `SkipSave=True` y nunca se llama
a `Save`. El cálculo de masa desactiva su caché en el documento. Se cotejan
SHA256 de los IAM/IPT/IPJ de entrada antes y después. El adaptador C#
`scripts/inventor_reference_resolver.cs` escucha `OnFileResolution` antes de
abrir cada referencia. Admite una ruta exacta dentro de la copia o un nombre
de archivo con una única coincidencia, excluyendo `OldVersions`. Se registra
la identidad interna esperada y se contrasta con los documentos cargados.
Cada intento queda en `reference_resolution`. No se guardan cambios de ruta;
los casos ambiguos o ausentes se dejan sin resolver, sin recurrir a originales
externos. Se debe completar el paquete y repetir antes de consumir resultados
parciales. El adaptador se compila con .NET y el interop de Inventor instalado.

`SkipAllUnresolvedFiles` permite elaborar un diagnóstico cuando faltan piezas;
no convierte una apertura parcial en éxito. Un resultado `partial_export`,
`blocked` o `source_integrity_failed` requiere atención. Código de salida 0
significa exportación sin incidencias registradas, 2 parcial/bloqueada y 3
modificación detectada en fuentes. El probe sólo comprueba la activación COM,
no la licencia de un documento concreto ni su capacidad de exportación.
`-SkipGeometry` permite obtener primero el inventario sin generar OBJ/STEP;
esas exportaciones quedan marcadas `not_requested`.
Los auxiliares conocidos de análisis `AIP/FEA` se conservan en la resolución
con estado `excluded_analysis_sidecar_outside_geometry_scope`; no se presentan
como piezas CAD faltantes ni como un análisis estructural validado. Un IPT sin
cuerpos de superficie ni conjuntos de mallas queda identificado por contadores
nativos como `non_surface_reference_geometry`, con bocetos y estructura BOM
registrados. No se le inventa una masa ni una malla de colisión.

## Contrato de salida

`cad_inventory.json`, esquema `uchuva.inventor_cad_inventory/1`, contiene:

- Versión de Inventor, PID privado, fechas, hash del exportador y tolerancia.
- Documentos únicos, ruta de copia, SHA256 y referencias faltantes/suprimidas.
- Ocurrencias con identidad jerárquica, documento asociado, visibilidad,
  supresión, estado de modelo y transformación local y acumulada.
- Restricciones y joints CAD, parámetros legibles, entidades y ejes de trabajo.
  Son evidencia bruta; ejes robóticos, ceros, límites y grupos rígidos necesitan
  una decisión trazable. Los subensambles flexibles se señalan para verificar
  sus transformaciones en contexto.
- Masa, centro de masa, volumen, área y momentos de inercia disponibles. La
  falta de propiedades se conserva como error, nunca se sustituye por cero.
- Apariencia nativa de documento y ocurrencia: nombre del asset, tipo de origen,
  colores RGB, parámetros escalares y material asignado cuando están disponibles.
  `diffuse_status=native_rgb` permite consumir `diffuse_rgb` (0–1) y conserva la
  propiedad nativa utilizada. Un color conectado a una textura o un shader no
  reconocido se marca pendiente; no se inventa una paleta para llamarla original.
- Estado y hash de cada exportación, incidencias e integridad de las copias.

Las matrices son 4×4 aplanadas por filas, actúan sobre vectores columna y
representan `parent_T_child`. Las traslaciones están en metros. La matriz
acumulada se calcula `root_T_parent × parent_T_child`. Cada raíz de ensamblaje
tiene su propio marco; tres subensambles separados no definen sus montajes.

Inventor trabaja internamente en cm, kg y rad. Se convierten longitudes por
0,01, áreas por 0,0001, volúmenes por 0,000001 e inercias por 0,0001. Los
momentos XYZ se conservan en orden `Ixx,Iyy,Izz,Ixy,Iyz,Ixz`, alrededor del
centro de masa y en ejes del documento. Los términos cruzados son entradas
directas del tensor simétrico: se reordenan para SDF, sin negar su signo. El
exportador contrasta traza, segundo invariante y determinante con los momentos
principales nativos (tolerancia relativa 10⁻⁶). El test incluye un tensor
asimétrico de autovalores conocidos y rechaza la negación de los tres términos
cruzados. La consistencia algebraica no valida densidades del prototipo. Una masa
derivada del sólido CAD no representa automáticamente relleno de impresión,
componentes internos ni masas medidas.

`meshes/doc_NNNNN.obj` contiene facetas por pieza en metros y marco del documento,
con normales. No aplica la transformación de ocurrencia: el consumidor debe
aplicarla una sola vez. La tolerancia es la desviación cordal máxima solicitada
a Inventor; no es precisión de medición. Los ensamblajes se componen desde sus
ocurrencias para conservar movilidad y huecos. Los colores se entregan como
metadatos separados; no se exportan texturas ni overrides por cara originales
ni se crea una envolvente convexa de la máquina.

`step/doc_NNNNN.stp` procede del traductor AP214. El propio STEP declara unidades;
no se debe aplicar ciegamente otro factor 0,01 al importarlo. STEP/OBJ no
transportan por sí solos toda la cinemática, los materiales ni las masas.

## Referencias estándar ausentes

`scripts/generate_inventor_standards.ps1` consulta las familias instaladas BS 290
SKF, DIN 6885-1 A e ISO 10642. Sin `-SelectionFile`, escribe el catálogo de
familias, revisiones, columnas, unidades y filas disponibles. Con una selección
JSON explícita, crea un proyecto privado bajo la nueva carpeta de salida,
activa el proyecto sólo para esa sesión (`Activate(False)`) y dirige su caché de
Content Center a esa misma carpeta. No cambia el proyecto predeterminado.

```powershell
powershell.exe -NoProfile -STA -File scripts/generate_inventor_standards.ps1 `
  -OutputDirectory outputs/real_harvester_cad/catalogo_nuevo

powershell.exe -NoProfile -STA -File scripts/generate_inventor_standards.ps1 `
  -OutputDirectory outputs/real_harvester_cad/estandares_nuevos `
  -SelectionFile outputs/real_harvester_cad/content_center_selection.json
```

Cada entrada de `members` en la selección contiene `requested_basename`,
`family_content_identifier`, `family_revision_id`, `row_content_identifier`,
los valores y unidades de la fila inspeccionada y la justificación de selección.
No se selecciona un rodamiento por diámetro solamente: la designación debe
conservar su variante de sellado. Una edición de norma escogida cuando la
referencia original no la declara se registra como elección explícita.

`CreateMember` genera sólidos de biblioteca con identidades nuevas. El informe
`content_center.json` conserva familia, revisión, fila, ruta, SHA256 e identidad
generada, con procedencia `GeneratedContentCenter`. Esto no recupera la identidad
del archivo original ausente ni valida la masa del producto comprado. No se
modifican los originales para aparentar esa identidad.

Para probar la resolución, se puede crear otra carpeta de staging copiando el
paquete descargado y añadiendo los miembros generados. Pasar su informe mediante
`-GeneratedMembersManifest` al exportador identifica los equivalentes por SHA256
y conserva los GUID esperados y cargados distintos en la evidencia. Las fuentes
descargadas y el staging se mantienen separados; ninguno se guarda desde Inventor.
Si el ensamblaje rechaza una referencia, se conserva el fallo y se usa un mapeo
explícito de equivalencia aguas abajo, sin fingir resolución completa.

## Derivado para orientación de facetas

La asociación nativa es una normal por vértice y los índices empiezan en uno.
`scripts/repair_inventor_mesh_winding.py` permite generar otra carpeta cuando
la auditoría detecta triángulos orientados en sentido contrario a esas normales.
Conserva literalmente todas las líneas de vértices y normales; invierte sólo el
orden de los índices de la cara si el producto con la normal nativa media es
negativo. Descarta triángulos cuya norma del producto vectorial sea menor que
10⁻¹⁵ m², el mismo criterio de degeneración de la auditoría.

```powershell
python scripts/repair_inventor_mesh_winding.py `
  --inventory outputs/real_harvester_cad/export_full_01/cad_inventory.json `
  --output outputs/real_harvester_cad/export_winding_repaired_nuevo

python scripts/audit_cad_meshes.py `
  --inventory outputs/real_harvester_cad/export_winding_repaired_nuevo/cad_inventory.json `
  --output outputs/real_harvester_validation/cad_mesh_repaired_nuevo
```

`mesh_repair_report.json` registra SHA originales y derivados, número de línea,
índices de cada cara modificada, producto normal y área cruzada. El inventario
derivado conserva el estado y todas las incidencias originales; la reparación
no convierte el inventario nativo parcial en un PASS. No modifica STEP, fuentes,
tolerancia cordal, escalas, transformaciones ni propiedades inerciales. Se debe
repetir la auditoría con sus criterios originales antes de consumir el derivado.
Esto alinea facetas con las normales que entregó Inventor; no valida la forma
contra medidas del prototipo.

## Ejecución y evidencia del 23 de noviembre de 2026

La matriz compacta versionada
[`real_harvester_cad_inventory_2026-11-23.json`](../references/real_harvester_cad_inventory_2026-11-23.json)
registra las tres raíces con revisión y SHA256, los once estándares y los hashes
de cada informe. Los 162 IAM/IPT descargados conservan sus SHA de descarga y
coinciden con las copias de staging. Inventor verificó intactos los 173 archivos
de staging tras añadir los once miembros estándar.

Se generaron desde las bibliotecas instaladas SKF BS 290: 6000-2RS1, 6007-RS1,
608-2RS1, 608-RS1, 61902-2RS1, 61902-RS1 y 623-2Z; DIN 6885 A: 2×2×12,
3×3×20 y 5×5×32 mm; e ISO 10642 M4×16. Diez nombres corresponden exactamente
a filas de biblioteca. Para el tornillo se eligió explícitamente la edición
ISO 10642:1997, porque el nombre de la referencia original no indicaba edición.
Son archivos nuevos `GeneratedContentCenter`, no una recuperación de los GUID
de los archivos originales ausentes.

`export_full_01` contiene 135 documentos, 306 ocurrencias resueltas, 102 OBJ y
135 STEP. Su estado original permanece `partial_export`: 59 auxiliares de FEA
fuera de alcance y cuatro errores de masa/facetas en dos IPT sin geometría
de superficie. La pasada nativa posterior `inventory_appearance_01` comprobó
que ambos sólo contienen geometría de referencia/bocetos, sin cuerpos ni
conjuntos de mallas, y terminó sin incidencias. No se atribuye masa a esos IPT.

La primera auditoría geométrica quedó en **FAIL, 22 mallas**. El derivado
`export_winding_repaired_01` invirtió 258 caras y eliminó un triángulo degenerado;
la reauditoría pasó **102/102** con las mismas tolerancias. La comparación
independiente confirmó líneas `v/vn` idénticas, y conservación de ocurrencias,
transformaciones, masas y las incidencias originales. El FAIL inicial no se
sobrescribió.

El paquete `robot_package_02` agrega 239 ocurrencias físicas en 11 enlaces y
90 mallas únicas, con 18,2498786605 kg derivados de CAD. De sus 239 ocurrencias,
238 usan color CAD; el tornillo con textura conectada usa una apariencia de
inspección declarada. `wallpaint_color` conserva los colores gris oscuro,
canario y cian de los assets nativos. No se afirma equivalencia exacta entre
shaders de Inventor y Gazebo. El paquete es **diagnóstico**, con suspensión y
pinza congeladas; no tiene aceptación de cosecha ni validación del hardware.

`outputs/real_harvester_cad/manual_sources_package_02/manifest.json` congela
los mappings de brazo/base y las hipótesis con SHA coincidentes con los inputs
del paquete. Incluye el perfil nominal incompleto como contexto, identificado
expresamente como archivo que no se usó de entrada del constructor. También
conserva la versión exacta del constructor y referencia el perfil generado.

La fotografía parcial tiene SHA256
`ce728cf18ad97c7325f8ef22a5ba372f626ae10975166ac95a9ed1bfccf3a470`; la copia coincide
con el archivo proporcionado en el checkout original. Se ven estructura
metálica clara, ruedas y soporte cilíndrico negros, electrónica y cableado.
Esas categorías son visualmente compatibles con algunos materiales del CAD,
pero no prueban una coincidencia completa del prototipo, aleación, masa,
dimensiones, colores calibrados ni montaje del brazo y pinza completos.
La foto y los CAD permanecen fuera de Git.

## API oficial utilizada

- [Unidades de base](https://help.autodesk.com/cloudhelp/2023/ENU/Inventor-API/files/UnitsTypeEnum.htm).
- [Apertura con opciones](https://help.autodesk.com/cloudhelp/2027/ENU/Inventor-API/files/Documents_OpenWithOptions.htm) y
  [cierre sin guardar](https://help.autodesk.com/cloudhelp/2027/ENU/Inventor-API/files/Document_Close.htm).
- [Facetas y sus índices desde uno](https://help.autodesk.com/cloudhelp/2027/ENU/Inventor-API/files/SurfaceBody_CalculateFacets.htm).
- [Momentos XYZ alrededor del centro de masa](https://help.autodesk.com/cloudhelp/2023/ENU/Inventor-API/files/MassProperties_XYZMomentsOfInertia.htm).
- [Exportación STEP oficial](https://help.autodesk.com/cloudhelp/2024/ENU/Inventor-API/files/SaveAsSTEPTranslator_Sample.htm).
- [Definición de joints CAD](https://help.autodesk.com/cloudhelp/2027/ENU/Inventor-API/files/AssemblyJointDefinition.htm).
- [Resolución de referencias antes de abrirlas](https://help.autodesk.com/cloudhelp/2027/ENU/Inventor-API/files/FileAccessEvents_OnFileResolution.htm).
- [Generación de miembros de Content Center](https://help.autodesk.com/cloudhelp/2027/ENU/Inventor-API/files/ContentFamily_CreateMember.htm),
  [ruta de caché del proyecto](https://help.autodesk.com/cloudhelp/2027/ENU/Inventor-API/files/DesignProject_ContentCenterPath.htm) y
  [activación sin cambiar el predeterminado](https://help.autodesk.com/cloudhelp/2027/ENU/Inventor-API/files/DesignProject_Activate.htm).

Los artefactos CAD y sus derivados grandes permanecen en `outputs/`, fuera del
historial. Conservar sus términos originales y procedencia; no publicar originales
privados. Las pruebas de helpers verifican conversiones y composición de marcos,
no sustituyen la apertura y comparación nativa de un ensamble conocido.
