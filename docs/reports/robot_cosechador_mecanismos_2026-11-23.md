# Cosechador CAD: mecanismos e interferencias

## Estado de esta continuación

El perfil articulado de referencia 09 conserva las 239 piezas físicas y los
18,2498786605 kg calculados por el CAD. Las revisiones locales posteriores
recalculan explícitamente la masa de la pieza modificada y la inercia de su
conjunto rígido. La masa no procede de una pesada del prototipo. Los
ensayos históricos siguen conservados; sus PASS no validan el nuevo modelo.
La misión de tres objetivos V8 y su vídeo permanecen **NO EJECUTADOS** mientras
fallen las pruebas del mecanismo completo. No se han movido plantas, frutos ni
ramas, ni ampliado las tolerancias de aceptación.

## Interferencia que requiere revisión del diseño

Inventor evaluó los sólidos de `Gripper y engranaje:1` y `Eslabon L:1` del
ensamblaje `gripper/Gripper ensamble.iam`. La postura cero es la guardada en
el CAD. Las demás posturas siguen la rama cinemática continua del mecanismo
de cuatro barras reconstruido a partir de sus pivotes; se aplican a copias
temporales sin modificar los documentos o restricciones originales.

El ángulo de la tabla corresponde al incremento del engranaje conductor de
la pinza, **no** al ángulo absoluto de la mordaza ni a una articulación del
brazo. Los dos engranajes giran en sentidos opuestos.

| Incremento conductor | Separación mínima CAD | Volumen común CAD |
|---|---:|---:|
| 0 rad / 0° | 1,804884 mm | 0 mm³ |
| 0,04 rad / 2,2918° | 0,744487 mm | 0 mm³ |
| 0,065 rad / 3,7242° | 0,107660 mm | 0 mm³ |
| 0,070 rad / 4,0107° | 0 mm | 0,018335 mm³ |
| 0,100 rad / 5,7296° | 0 mm | 6,617663 mm³ |

4,0107° es la **primera muestra positiva del barrido**, no una estimación
exacta del instante inicial de contacto. El intervalo anterior acota la
transición entre 3,7242° y 4,0107°. El volumen común positivo es una
interferencia de sólidos, independiente de la proyección o la oclusión visual.
Estos datos no demuestran cómo se deformaría una pieza fabricada.

Evidencia local privada, excluida de Git:

- `outputs/real_harvester_validation/gripper_native_interference_01/result.json`:
  cinco pares de sólidos en postura cero, sin interferencia.
- `outputs/real_harvester_validation/gripper_native_envelope_01/result.json`:
  21 posturas, 105 pares inspeccionados y hashes de los originales inalterados.
- `outputs/real_harvester_validation/gripper_brep_motion_010.json`:
  transformaciones rígidas que reproducen cada postura del barrido.
- `outputs/real_harvester_validation/gripper_collision_geometry_01/result.json`:
  extracción adicional de las dos piezas y del cuerpo común nativo en 0,
  0,07 y 0,10 rad, con teselación de 1 µm para las figuras. Se verificaron
  inalterados los hashes de 162 documentos originales. A 0,10 rad, el
  centroide del volumen común está en `[27,11138; 2,00116; 0,11093]` mm,
  expresado en el marco local del ensamblaje de la pinza.

El usuario solicitó imágenes para determinar el arreglo. Cualquier cambio
posterior de forma, montaje o flexibilidad deberá quedar como revisión
explícita. No se ha excluido del cálculo la pareja que se interpenetra.

La sección comparativa está en
`outputs/real_harvester_validation/gripper_collision_section_02/seccion_comparativa.png`
y en SVG en el mismo directorio. La sección es el plano Y = 2 mm del marco
CAD, con idéntico encuadre X/Z y escala en ambas posturas. El rojo procede del
cuerpo de intersección calculado por Inventor, no de una estimación visual.
Se observa el borde de la orejeta del eslabón alrededor del pasador entrando
en la pared inclinada de la carcasa. `section_geometry.json` conserva los
contornos, las fuentes y sus hashes; el script reproducible es
`scripts/render_cad_interference_section.py`.

## Resultados independientes ya observados

| Ensayo | Estado | Alcance |
|---|---|---|
| `fk_cad_control_01` | PASS, 11/11 | Revisión de control del brazo con mecanismos congelados; no valida el robot articulado completo. |
| `native_loops_01` | PASS | Cierres nativos de suspensión y pinza; controles con cierre desconectado fallan como se esperaba. |
| `gripper_gears_rotated_pgs_01` | PASS | Banco de engranajes rotado con PGS; error máximo 0,000115151 rad frente a 0,001 rad. |
| `dynamic_concave_mesh_04` | PASS, 9/9 | Contactos dinámicos en cavidades cóncavas con esfera y malla, también rotadas. |
| `mesh_collision_masks_01` | PASS, 6/6 | Parejas excluidas, requeridas y externas entre mallas/primitivas; tolerancia original de 5 mm. |
| `cad_gripper_contact_02` | FAIL | No alcanzó la apertura solicitada de 0,04 rad; velocidad nativa máxima 1,48444 rad/s. |
| `video_preflight_01` | PASS técnico | 32 imágenes RGB nativas codificadas y decodificadas; inspección estática, sin cosecha. |

En `cad_gripper_contact_02` los cierres y la relación de engranajes quedaron
dentro de sus umbrales, pero la pinza no abrió. Los sensores de las gomas no
observaron contactos; no llegó a crearse el testigo de pedicelo ni a ejecutarse
ARM/CUT o retención. No se atribuye este atasco a la interferencia de 4,01°:
el comando de ese banco era menor y el ángulo observado apenas avanzó. Falta
identificar las parejas internas involucradas en el atasco dinámico. Esa
identificación se completó después en los ensayos causales descritos abajo.

La representación de colisiones conserva la concavidad del CAD. La revisión
de orientación y cierre de mallas admite 87/87 activos de colisión en
`collision_asset_admission_06.json`. Las reparaciones derivadas están
identificadas por hash; las mallas visuales y los CAD originales se conservan.
El único ajuste de coordenadas es una normalización explícita de costura de
hasta 5 nm en una malla de colisión; no es una modificación del diseño.

## Reproducción y límites

La guía [Mecanismos cerrados CAD en Gazebo](../guides/mecanismos_cerrados_cad_gazebo.md)
describe los bancos, la observación nativa y los fallos conservados. El archivo
`configs/robots/cad_v8_acceptance_lock.json` mantiene las fuentes, identidades y
criterios de aceptación de V8. El grabador nativo preparado no transforma un
ensayo estático en un vídeo de misión.

La integración completa aún requiere estabilidad, apertura útil, límites
articulares, contactos y seguimiento observados en el mismo paquete físico;
después, planificación viable sin modificar los objetivos, ciclo individual
y misión. Los avances de bancos aislados no permiten omitir esas etapas.

Durante la preparación de las figuras pasaron 72 pruebas `test_robot*.py`,
97 pruebas `test_harvest*.py` y 11 pruebas de mecanismos, cierres y refinamiento
de colisiones. El validador del contexto informó 158 nodos y 267 relaciones
válidos. `v8_invariance_02.json` verificó los seis hashes del cultivo, los tres
objetivos, sus poses y el manifiesto congelado. Son comprobaciones de software
e integridad y no sustituyen las pruebas físicas pendientes.

## Continuación con la carrera corta del prototipo

La fotografía y la declaración del usuario se registran en
[observaciones del prototipo](../references/real_harvester_prototype_observations_2026-11-23.json).
Los **8 mm rígidos y 6 mm flexibles son aproximados**; no se convierten en
mediciones calibradas ni en una relación entre consigna del servo y ángulo.
En el CAD, q = 0,084810927651 rad da 8,390804 mm entre L1/L2 y 6,006657 mm
entre gomas. Los portagomas y las cuchillas son otras parejas de superficies.

La copia `clearance_revision_03` modifica únicamente L1. Conserva el agujero,
los ejes, las poses, L2 y los 162 archivos originales. Retira 4,516497 mm³
(5,555291 mg según la densidad CAD), sin validación de resistencia. El
integrador `apply_cad_part_revision.py` verifica el agregado de inercia previo
y sustituye únicamente la geometría 104 y la inercia de su mordaza. Las
88 mallas resultantes pasan la admisión geométrica; esto no valida la física.

El barrido revisado contiene 90 posturas y 900 evaluaciones BRep, sin
intersecciones volumétricas. La pareja carcasa/L1 tiene una separación mínima
de 0,127712 mm y cota continua nominal de 0,081971 mm: **no cumple la reserva
de diseño de 0,200 mm**. Se conserva ese fallo y se prepara un ajuste local
adicional, manteniendo el ligamento mínimo de 1,900 mm al agujero. Las dos
parejas tapa/L permanecen tangentes; cero distancia no prueba solapamiento ni
cumplimiento de un margen. Ninguna de estas cifras constituye PASS de los
4 mm operativos ni autoriza excluir enlaces completos de las colisiones.

## Diagnóstico nativo de contactos, control y giro

ODE genera contactos tapa/L desde q = 0, aunque Inventor no encuentra volumen
común: máximos de 1,1468 mm y fuerzas de hasta 2370,6 N por observación de
contacto. Los mensajes repetidos por sensores no se suman como fuerza neta.
FCL también falla en el mecanismo; sus mensajes iniciales de construcción no
demuestran ausencia de mallas, porque Gazebo usa después `AttachMeshShape`.
Bullet pasó nueve controles de concavidad y seis de máscaras/contacto; esto
admite ensayar ese detector, no transfiere PASS al robot completo.

El nuevo controlador por esfuerzo limita la referencia en cada paso físico
y deriva la velocidad medida. Conserva un único escritor `JointForceCmd` y
publica esfuerzo solicitado/limitado, saturación, rechazo de órdenes y máximos
por ventana. La auditoría contrasta el esfuerzo con el observador independiente
del mismo paso, sin emparejar por tiempo aproximado. Un estado inicial aún
no disponible se registra explícitamente y nunca cuenta como cobertura lista.

La observación a 10 kHz detectó una oscilación alternante de 5 kHz incluso
con consigna cero. El análisis de inercias y la prueba causal justifican probar
amortiguación del engranaje de 0,012 en lugar de 0,030 N·m·s/rad, manteniendo
K = 100 N·m/rad, los PID, 100 µs de integración y todos los límites. En el
banco `cad_gripper_bullet_ramped_c012_01` de 1,2 s, el conductor alcanza
0,039915 rad, el máximo articular es 0,567553 rad/s y el error de engranajes
1,975·10⁻⁶ rad. Sigue siendo un banco parcial, anterior a la carrera de 6 mm
y al candidato integrado definitivo.

El protocolo completo `cad_mobility_mesh_repaired_09` conserva FAIL: avanza
0,193424 m, pero gira sólo 2,231·10⁻⁶ rad y presenta velocidades excesivas
en la pinza. El ensayo aislado con límite estimado de 6,5 N·m gira 0,209822
rad, todavía por debajo de 0,250 rad. La revisión PI 04 se deriva de las
cargas desiguales observadas en las ruedas y sigue pendiente de prueba en
el candidato común. La capacidad de 6,5 N·m es una hipótesis de simulación,
no un par continuo demostrado del motor instalado.

Los registros antiguos no se sobrescriben. Los nuevos protocolos conservan
el código de salida nativo antes de cualquier posprocesado y recogen un paso
adicional de observación para emparejar la pose final con su respuesta física;
no prolongan las fases de movimiento ni cambian los umbrales. La misión V8
y el vídeo de cosecha permanecen **NO EJECUTADOS** hasta superar estas etapas.
