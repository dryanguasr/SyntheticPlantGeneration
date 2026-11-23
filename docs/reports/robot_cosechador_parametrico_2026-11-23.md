# Cosechador paramétrico: implementación y diagnóstico CAD

Fecha: 2026-11-23. Rama: `codex/gazebo-real-harvester-parametric`, creada desde
`origin/main` en `3306372ee214a862384fac2e5f5f69f2960d41a5`.

Se implementó el contrato paramétrico y se obtuvo un robot articulado a partir
de los ensamblajes finales. **La aceptación completa del cosechador todavía no
está alcanzada.** Hay evidencia de geometría CAD, de consistencia numérica y de
infraestructura nativa; los mecanismos cerrados, la dinámica del conjunto y la
cosecha mantienen resultados separados. Los PASS del piloto histórico no se
trasladan al robot nuevo.

## Fuentes y modelo entregado

Se abrieron en Inventor 2027 `Ensamble brazo v2.iam`, `Locomoción armada V3.iam`
y `Gripper ensamble.iam`. Las 162 copias originales permanecen intactas. Se
generaron once piezas normalizadas equivalentes desde Content Center instalado:
siete referencias SKF, tres chavetas DIN 6885 A y un tornillo ISO 10642 M4×16.
La edición 1997 del tornillo es una decisión explícita; la referencia original
no indicaba edición. Los equivalentes tienen identidades distintas y no se
presentan como los archivos originales recuperados.

La exportación contiene 135 documentos y 306 ocurrencias resueltas. Hay 102
mallas de piezas y 135 STEP de referencia. Dos documentos de construcción no
tienen cuerpos superficiales ni mallas; su exclusión se apoya en contadores
nativos de Inventor. Se conservan 59 referencias auxiliares de resultados FEA
ausentes, sin confundirlas con piezas mecánicas faltantes.

El paquete integrado `outputs/real_harvester_cad/robot_package_02` contiene:

- `cad_diagnostic_frozen.json`: 11 links, 239 ocurrencias físicas, 90 mallas
  únicas, cinco articulaciones de brazo y cuatro ruedas. Su SHA de configuración
  es `7e7c18dd668261695229af9eaba905c1aa7377405796c7d835fd830aa669cb50`.
- `cad_nominal.json`: conserva la geometría disponible y los pendientes que
  impiden admitir el modelo nominal completo.
- `model.sdf`, `robot_contract.json`, las mallas privadas y
  `cad_import_report.json`, con procedencia y asignaciones por ocurrencia.

La suma de masas de hojas es **18.2498786605 kg de CAD**, sin baterías ni cesta
incorporadas. No es una pesada. El material/relleno, componentes comprados y
sobrescrituras CAD requieren contraste físico. Las masas de ensamblajes no se
suman otra vez a sus piezas. La pequeña diferencia frente a los totales de raíz
se conserva; no se corrigen valores para hacerlos coincidir.

Las dimensiones extraídas incluyen separaciones entre ejes de brazo de 280 y
260 mm, radio CAD de neumático de 110 mm, vía de 616.55 mm y batalla de
621.1563867 mm. El texto «8in» del archivo no se usó como medida. La muñeca
aparece como pitch seguido de roll. El eje del servo del codo está desplazado
por la transmisión y no se utilizó como eje de la articulación.

La fotografía aportada por el usuario acredita un ensamblaje parcial y respalda
el centrado lateral y el desplazamiento hacia atrás descritos por él. Su SHA es
`ce728cf18ad97c7325f8ef22a5ba372f626ae10975166ac95a9ed1bfccf3a470`.
No acredita distancias métricas, el brazo completo instalado ni capacidades.
El montaje numérico `[-0.06, 0, 0.15446684] m` permanece estimado, con incertidumbre
explícita. Los límites diagnósticos de ±15° tampoco son topes de hardware.

## Geometría y representación compartida

`RobotSpec` y `ResolvedRobot` resuelven unidades SI, validación, procedencia,
overrides y hashes. La API pública alimenta SDF, FK, IK acotada, colisiones y
contrato. Se rechazan ejes inválidos, inercias imposibles, unidades incompatibles,
referencias ambiguas, activos alterados y longitudes que exigirían reexportar
mallas congeladas. El proxy sigue siendo una vía explícita.

La auditoría inicial de las 102 mallas falló en 22 mallas por orientación de 258 facetas y
una faceta degenerada. La corrección derivada conserva todos los vértices y
normales, invierte únicamente el orden de las caras identificadas y retira la
faceta de área despreciable. Con las **mismas tolerancias**, la reauditoría pasó
102/102: índices, normales y envolventes SI. Se preservan exportación original,
fallo, receta, hashes y resultado reparado. No se cambió el CAD.

238 de las 239 ocurrencias físicas utilizan color difuso nativo de Inventor;
el tornillo con textura conectada usa una sustitución visual declarada. No se
afirma equivalencia fotométrica con los materiales PBR de Inventor. Las
colisiones del diagnóstico son cajas orientadas por pieza y cilindros para
los neumáticos. No acreditan cavidades interiores o contacto de mordazas; esa
limitación impide habilitar cosecha con este perfil.

## Pruebas y estados

Cada prueba nativa registra antes de arrancar su protocolo, tolerancias, perfil,
fuentes y binarios. Las salidas permanecen bajo `outputs/real_harvester_validation`.
Las revisiones sucesivas conservan los intentos anteriores. No se ampliaron
tolerancias para transformar fallos en éxitos.

| Etapa o dominio | Estado y alcance |
|---|---|
| A. Integridad, regresión y configuración | Pruebas de Python y helpers CAD; el inventario y las mallas preservan hashes. Conteo final en el registro de verificación. |
| B. Mallas CAD | PASS 102/102 tras reparación trazable; el FAIL inicial permanece. |
| B. FK del proxy | PASS 11/11 casos; evidencia de regresión, no del robot CAD. |
| B. FK/seguimiento CAD | Cobertura extendida: concordancia FK PASS 11/11, llegada angular 11/11 y estabilidad 1/11. Global FAIL, con el primer intento también conservado. |
| C. Actuación aislada | PASS nominal, masa duplicada y actuador insuficiente como negativo esperado; péndulo diagnóstico, no brazo CAD. |
| C. Exclusiones de contacto | PASS 3/3: cuerpos adyacentes excluidos, no adyacentes en contacto, control sin autocolisión. |
| C. Suspensión real cerrada | FAIL: DART rechaza la junta que cerraría el lazo; separación de ojos hasta 82.358 mm frente a 1 mm permitido. |
| C. Movilidad CAD | FAIL global; avance y parada PASS, giro y sostenimiento de brazo FAIL. 1.500 poses y 1.500 observaciones nativas. |
| C. Pinza cerrada | FAIL: DART rechaza la junta de cierre. Control abierto PASS con excursión de 0.1957465 rad; residual de cierre 7.254 mm frente a 0.5 mm. |
| D. Corte/retención aislados | PASS 5/5 casos de marcos desplazados, orientación incorrecta y guardas de captura. El latch sigue siendo idealizado. |
| D. Cosecha CAD V8 | NO EJECUTADO. Perfil sin `native_harvest`; no supera las condiciones de admisión física y de contacto. |
| D. Tres repeticiones de misión | NO EJECUTADO; dependen de una misión aceptada. |
| E. Parámetros CAD | PASS 4/4 de propagación estática: montaje, masa/posición de carga hipotética, techo de esfuerzo y rechazo de longitud. Dinámica de esas variantes: NO EJECUTADO. |
| Sensores y contraste con prototipo | NO OBSERVADO: no se asignan especificaciones, extrínsecos, ruido o latencia como datos medidos. |

En `fk_cad_03` el máximo desacuerdo entre poses nativas y FK con articulaciones
observadas es 1.00404e-6 m y 2.66760e-6 rad. No implica precisión frente al
hardware. La muñeca roll sigue oscilando cerca del límite de velocidad y no
cumple el criterio de estabilidad. Su pequeña inercia CAD y la ganancia derivativa
común justifican estudiar ganancias por articulación en una revisión posterior;
este informe no modifica el perfil evaluado para ocultar ese fallo.

En `gripper_loop_02` se ensaya un cuatro barras con ejes derivados del CAD y
propiedades de fixture declaradas como estimadas. El backend rechaza el cierre;
el control abierto se mueve y conserva la misma trayectoria que el cierre
ignorado. El primer intento, cuyo escalón ocurrió antes de la ventana de
observación de movimiento, también se conserva. La segunda secuencia introduce
órdenes a 0.5 y 1.2 s, manteniendo tolerancias y propiedades. No se validaron
sincronización de engranajes, contacto con goma ni fuerza de corte.

El observador distingue comando limitado, posición, velocidad, saturación y
wrench transmitido. Ninguno se etiqueta como torque de motor medido. La prueba
de lazo cerrado descubrió un componente wrench vacío para una junta rechazada;
se corrigió la disponibilidad para exigir coordenadas nativas finitas. El
intento `suspension_loop_03` comprueba `wrench_component_available=true` y
`wrench_available=false`, con fuerza transmitida nula en JSON.

En `cad_mobility_01`, el avance observado es 0.190447 m y la parada cumple el
criterio. La inclinación máxima es aproximadamente 3.33e-8 rad y la penetración
máxima de la envolvente de contacto es 0.0601 mm. El hombro satura 14.672 pasos a
3 Nm y llega al límite diagnóstico, con error de 0.261799 rad. Durante la orden
de giro no se observa rotación útil (aproximadamente 1.96e-10 rad). Los picos de
velocidad del hombro/codo/muñeca pitch alcanzan 0.851294/0.926704/0.917715 rad/s y
exceden el criterio de 0.30+0.03 rad/s. Se conserva el fallo; esas capacidades
son supuestos de diagnóstico, no evidencia de insuficiencia del hardware real.

El transporte contiene muestras cada 0.01 s durante toda la ejecución. Los
intervalos entre muestras que pasan los límites físicos se distinguen de la
cobertura bruta; una muestra que excede límites no desaparece del registro ni
se interpreta como pérdida de transporte.

Los árboles, poses e identidades V8 se conservan. El manifiesto del escenario
determina sus tres objetivos. La inspección estática con CAD no ejecuta una
misión ni sustituye sus estados por PASS. No se desplazan frutos o ramas para
obtener una solución.

La captura principal es
`outputs/real_harvester_validation/cad_v8_inspection_02/03_tool.png`.
El intento 02 conserva tres PNG, 415 muestras de estadísticas con mundo pausado
y tiempo simulado cero, y cierre correcto de ambos procesos. Renderizado nativo
Gazebo mediante D3D12/NVIDIA RTX 4050; modelos planta/fruto y recursos contrastados
por hash. Las dos primeras tomas no se presentan como perspectivas distintas
porque la cámara todavía se desplazaba. El intento 03 verifica una toma general
con pose observada y conserva un fallo de lectura temporal PNG sobre WSL/NTFS.
La corrección final del reintento de lectura no tuvo otra ejecución nativa.
No se presenta esta inspección como vídeo o misión dinámica.

## Pendientes para la aceptación completa

La suspensión congelada elimina el recorrido pasivo y la respuesta de muelles/
amortiguadores; la pinza congelada elimina apertura/cierre y fuerzas de contacto.
Conservan su geometría de referencia, pero no esos movimientos. El perfil
nominal requiere una representación dinámica admitida para los mecanismos.

Faltan montajes métricos contrastados, ceros/signos/topes reales, capacidades
continuas a la salida articular, pérdidas de transmisión, propiedades de
baterías/cesta, contactos con aberturas y especificaciones de sensores. La
calibración funcional del plano de corte/TCP también permanece pendiente. La
foto y los nombres de motores no resuelven esos datos.

La guía [robot_cosechador_parametrico.md](../guides/robot_cosechador_parametrico.md)
explica modificación y regeneración. La
[guía de extracción CAD](../guides/exportacion_cad_inventor_robot.md) conserva
el procedimiento Inventor y los equivalentes normalizados. Código, perfiles,
fuentes pequeñas y documentación se versionan; originales CAD, mallas, vídeos
y registros grandes quedan fuera del historial. Sólo se preparan commits
locales, sin push, PR ni merge.

## Registro de verificación de código

- Regresión de cosecha en WSL: 90 pruebas PASS. Después de la corrección del
  offset de depósito se ejecutaron las 15 pruebas de contrato runtime, incluida
  la nueva negativa con TCP y corte desplazados, todas PASS.
- Robot paramétrico: 40 pruebas PASS en la ejecución final, incluidas las
  16 pruebas de integración y la cobertura de máximos rechazados del auditor.
- Importación CAD e integridad de descarga: 10 pruebas PASS. Reparación de
  mallas: 3 pruebas PASS. Helpers PowerShell/COM: PASS.
- Compilación nativa de ambos plugins con Gazebo 8.14: PASS.
- Grafo de contexto: VALID, 158 nodos y 267 aristas.

La ejecución de pruebas del runtime con Python de Windows detectó la ausencia
esperada de `fcntl`; se ejecutó la regresión pertinente en WSL. No se etiqueta
esa ejecución de Windows como PASS.
