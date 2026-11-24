# Revisión de la orientación colgante del capacho

El usuario identificó numerosos capachos laterales en las muestras del banco.
Se detuvo el renderizador propio, verificando PID y tiempo de creación, antes
de admitir escenas o entrenar. El intento anterior se preservó íntegro en
`outputs/appearance_factorial_20261026/revisions/pendulous_orientation_20261027/`.
El presupuesto consumido permanece en el ledger; no se amplió ni reinició.

## Evidencia y causa

En los dos árboles adaptados actuales había 704 capachos. De ellos, 503 (71,4 %)
tenían su eje a más de 45° de la vertical hacia abajo. Las medianas por planta
eran 59,67° y 60,715°; el extremo llegaba a 85°. Son medidas tridimensionales del
modelo, no estimaciones de orientación del dataset ni tasas de oclusión.

El parámetro histórico del pedicelo describe **depresión desde la horizontal**.
La geometría prolongaba ese mismo eje para orientar el capacho; la reparación
permitía depresiones de 5–72°. Por tanto, resolver contactos podía producir un
capacho casi horizontal sin violar el contrato anterior. Las flores, además,
tenían una dirección ligeramente ascendente definida en el intérprete.

Se revisaron las notas de arquitectura nodal/axilar del proyecto y las fuentes
botánicas registradas. [Flora Zambesiaca, accesible en Kew](https://powo.science.kew.org/taxon/urn:lsid:ipni.org:names:195473-2/general-information)
describe variación entre posturas erectas e inclinadas/colgantes; la ficha de
[World Agroforestry](https://apps.worldagroforestry.org/usefultrees/pdflib/Physalis_peruviana_UGA.pdf)
describe flores solitarias colgantes. Ninguna de estas fuentes aporta una
distribución angular medida para las plantas de nuestros videos. La observación
local del usuario justifica corregir este banco hacia una apariencia
predominantemente colgante; no demuestra una orientación universal de la especie.

## Contrato nuevo y compatibilidad

El preset `trained_trellis_pendulous_audit_v7` conserva la arquitectura v6,
la activación nodal, órganos, dimensiones, clases y carga `architecture_driven`.
Asigna después de generar la arquitectura una postura reproductiva mediante
semillas independientes por órgano. El árbol serializado guarda el marco de
gravedad, inclinación desde abajo, acimut, límites, semilla y procedencia.

Se separan dos direcciones: el pedicelo sigue conectando la axila con el polo
proximal del órgano; el eje del cáliz y el desplazamiento del fruto siguen una
dirección colgante independiente. La reparación puede mover el pedicelo dentro
de su contrato, pero no convertir el capacho en un órgano lateral para escapar
de un contacto. Las flores del preset nuevo usan también la postura explícita;
no se alteran sus conteos ni estados.

El cono inicial de **0–25° desde abajo, moda 8°**, es una
`engineering_heuristic` pendiente de medición local. No es un valor normativo,
una medición de campo ni una simulación mecánica de gravedad/viento. Los presets
históricos sin esta política conservan su interpretación anterior explícita.
La nueva dirección se comparte entre geometría, proxies y adaptación de escena.

Los dos árboles convertidos conservan 704 frutos/capachos, 95 flores y 1.950
hojas. Sus nuevas medianas angulares son 10,40° y 9,94°. Se conservaron los
parámetros y hashes de origen, y se comprobó que el cambio autorizado no alteró
las partes protegidas del árbol. La conversión es una revisión científica
explícita; **no** se declara compatible por hash con las imágenes v6.

## Comprobación y uso en la campaña

La validación de morfología exige la postura cuando el snapshot la declara,
rechaza marcos desconocidos y valores no finitos/fuera de rango. Un auditor
adicional comprueba en la malla reconstruida el eje respecto a gravedad y la
coincidencia del polo proximal con el extremo del pedicelo. No certifica por sí
solo ausencia de intersecciones: permanecen las auditorías de malla y suelo.

Pasaron seis pruebas nuevas de generación, conservación, serialización,
validación e independencia frente a la reparación; diez fixtures Blender,
incluido el nuevo caso colgante con transformación de instancia, reparación,
reconstrucción y detección de una rotación incorrecta; quince pruebas previas de
copa baja y 23 del banco. Se mantienen las comparaciones B/L/T/LT emparejadas
sobre la misma geometría nueva. No se reutilizan RGB del intento anterior.

La comparación visual usa cámaras fijas, ambos perfiles de apariencia aprobados
y los mismos árboles antes/después; es un diagnóstico provisional. La aceptación
de escenas del banco requiere repetir el control de intersecciones y terreno
con la orientación corregida. Todavía no hay evidencia de una mejora de AP.

La galería local quedó en
`outputs/appearance_factorial_20261026/revisions/pendulous_orientation_20261027/fixed_camera_preview/index.html`.
Se verificó igualdad de cámaras y perfiles efectivos entre ambas versiones.
Se reanudó el controlador con fuentes 2.4 congeladas y árboles convertidos
verificados. El primer audit previo a reparación todavía detecta intersecciones;
no es una escena aceptada. La postura colgante no exime de resolverlas.

## Recuperación técnica del auditor (27/10, 06:52 UTC)

El intento 2.4 terminó con 462 pares de intersección pendientes y suelo válido.
Además, el auditor de orientación abortó el controlador por una discrepancia
numérica en **uno de 704** capachos: inclinación de 0,069596°, acimut 81,221324°
y error de dirección de 1,86×10⁻⁵ frente al umbral 10⁻⁵. La transformación
`to_track_quat` perdía precisión cerca de la vertical; no era un capacho lateral
ni un fallo de conexión (error de unión de 3,51×10⁻⁶ unidades Blender).

Se conservó íntegro ese intento y se implementó en 2.5 un marco transversal
estable, proyectando X de la planta sobre el plano normal al eje del órgano.
Ese giro axial antes no estaba medido ni restringido por el contrato; ahora
queda determinado de forma reproducible. Se usa el mismo marco al construir
la malla y al evaluar candidatos analíticos de reparación. La ruta histórica
conserva su marco anterior. **No se aumentaron las tolerancias**, el cono
angular ni los umbrales de intersecciones o suelo.

Pasaron once fixtures Blender, incluyendo la regresión cerca de ±Z y la
reconstrucción del caso capturado. La reconstrucción completa de los mismos
704 capachos pasó el auditor sin errores. Esto certifica orientación/conexión,
no contactos: el intento previamente rechazado se excluye conservadoramente
y no se reutiliza como geometría aceptada. Continúan los siguientes intentos
con semillas distintas, los perfiles de luz/materiales aprobados y el consumo
de tiempo anterior conservado. Todavía no hay escenas admitidas ni AP nuevo.

## Pedicelos florales en la representación de búsqueda (27/10, 08:22 UTC)

El siguiente intento terminó correctamente las auditorías de orientación, pero
se rechazó por 1.261 intersecciones pendientes, con suelo válido. Durante la
preparación del intento 02 apareció otro defecto de implementación: la rutina
de proxies salía anticipadamente cuando una unidad no tenía cáliz. Las flores
sí tenían pedicelo en la malla; por eso un contacto medido entre un pedicelo
floral y otra rama no encontraba su representación de búsqueda y abortaba el
controlador.

La versión 2.6 representa también esos pedicelos bajo la política nueva,
conservando la ruta histórica. No agrega cálices a flores, no altera estados,
conteos, dimensiones, posturas ni clases y no elimina contactos de la auditoría.
Se reconstruyó el caso capturado: las 179 y 170 restricciones de ambas plantas
encuentran proxies después de la corrección. Pasaron 19 pruebas de reparación
de ejes, seis de orientación y 23 del banco. Estas verificaciones no certifican
validez física ni equivalen a una escena admitida.

Se preservó íntegra la versión anterior, incluidos rechazos y el intento
interrumpido antes de modificar poses. Se continúa ese intento desde sus árboles
iniciales verificados por hash, conservando rechazos anteriores y consumo activo.
Las condiciones de admisión, el presupuesto y el protocolo de entrenamiento
permanecen iguales. El entrenamiento todavía no ha comenzado.
