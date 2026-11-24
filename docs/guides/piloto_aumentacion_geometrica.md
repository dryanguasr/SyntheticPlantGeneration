# Piloto de aumentación con encuadres comparables

Campaña del 22 de octubre de 2026: comparar detección y clase de apariencia
del capacho, sin interpretar las etiquetas como madurez interna validada.
El presupuesto máximo es de 24 horas desde las 09:54:59 de Colombia,
con parada de entrenamiento a las 22 horas y de renders a las cuatro horas.

## Datos y admisión

La fuente es la unión depurada del piloto real del 22 de octubre: 461 imágenes
train, 88 val y 94 test de desarrollo ya consultado. Las exclusiones y grupos
se conservan. La geometría del generador se ajusta únicamente con train.
Los presupuestos agrupados anidados son 125, 210 y 461 imágenes; no se separan
grupos para forzar 25/50/100 por ciento exactos.

Las nuevas vistas conservan morfología y materiales del intérprete congelado,
con semillas de plantas de entrenamiento. Cambian cámara y encuadre, no tamaño
de órganos. Todas las instancias con píxeles visibles conservan anotación.
Por instrucción posterior del usuario, antes del entrenamiento comparativo,
la densidad se conserva como medida descriptiva y deja de bloquear admisión.
El banco se admite con error relativo máximo de 20 por ciento en la mediana
de tamaño, y diferencia máxima de cinco puntos porcentuales en cada
intervalo del lado menor a 960: menos de 16, 16–32, 32–64 y al menos 64 píxeles.
La admisión se comprueba para cada subconjunto y proporción antes de entrenar.
Un banco insuficiente o rechazado por tamaños bloquea su mezcla. Los umbrales
de tamaño no cambian. La revisión autorizada y el protocolo anterior se conservan
en `revisions/01_density_gate_removed/` dentro de la campaña.

## Comparación

Se cruzan tres presupuestos reales, cuatro adiciones sintéticas (0/25/50/100
por ciento respecto al número de imágenes reales) y aumentación clásica
desactivada/activada. La receta clásica aplica reflejo horizontal con p=0,5
y HSV-valor 0,1; no cambia tono ni saturación. Se desactiva la aumentación
opcional dependiente de Albumentations. No se instalaron dependencias.

El adaptador usa el entrenador nativo de Ultralytics, yolo26n.pt por hash,
entrada 960, batch=2, nbs=2, AdamW y LR inicial 0,0002. Una época técnica
contiene exactamente 500 actualizaciones, independientemente del dataset.
El LR decrece linealmente por actualización hasta el uno por ciento del inicial.
AMP usa escala inicial 1, común a todos los brazos; una actualización omitida
invalida la corrida. No se modifica el entrenamiento histórico.

El screening tiene 2.000 actualizaciones y una semilla. Los finalistas se
seleccionan por AP50–95 macro en validación y se reinicializan para 4.000
actualizaciones con tres semillas. El test no participa en esa selección.
Se registra exposición por imágenes e instancias: iguales pasos no implican
igual exposición real. Para una mezcla ganadora admisible se añade repetición
real con la misma secuencia planificada de muestreo.

## Ejecución y trazabilidad

Los scripts `augmentation_pilot.py`, `prepare_augmentation_renders.py`,
`audit_augmentation_renders.py`, `run_augmentation_campaign.py`,
`train_augmentation_arm.py`, `evaluate_augmentation_campaign.py` y
`report_augmentation_campaign.py` guardan los artefactos en
`outputs/augmentation_pilot_20261022/`. El directorio de preparación es nuevo;
no sobrescribe una campaña existente. Las corridas completas pueden recuperarse
por hashes; no se admite reanudar un entrenamiento parcial con fuentes cambiadas.

El informe distingue pruebas técnicas, screening, finalistas, mezclas bloqueadas,
variación por semilla e incertidumbre de remuestreo por grupos. La independencia
por sesión no está demostrada. No se publican ni promueven pesos automáticamente.

## Extensión exploratoria autorizada con sintéticos

El usuario solicitó posteriormente probar los sintéticos disponibles aunque
incumplan los criterios de tamaño. Esta autorización se registra por separado
en `outputs/augmentation_pilot_20261022/synthetic_exploratory_extension/authorization.json`.
No cambia el protocolo ni los resultados de los controles reales en curso.

La extensión usa las 389 capturas técnicamente verificadas, incluidas las doce
de calibración, y conserva todas sus etiquetas. Cruza tres cantidades reales
con adiciones sintéticas de 25/50/100 por ciento y clásica desactivada/activada.
Con 461 reales, la última adición queda limitada a 389 sintéticas (84,38 %),
sin duplicar imágenes para aparentar un banco mayor. Las proporciones se refieren
a sintéticas/reales, no al porcentaje sintético de la mezcla total.

`scripts/run_synthetic_exploratory_extension.py` espera el cierre del proceso
original para evitar competencia por GPU, verifica y reutiliza sus controles por
hash, y ejecuta las mezclas con el mismo entrenador congelado. Mantiene los
límites originales de entrenamiento y evaluación. Selecciona proporciones solo
por validación y reporta el desajuste de tamaños como limitación, no como una
admisión geométrica exitosa. `scripts/evaluate_synthetic_extension.py` conserva
la evaluación y genera un informe separado de la campaña real/clásica.
## Cierre por presupuesto (23 de octubre de 2026)

La extensión cerró con 17/18 brazos sintéticos de screening completos y seis
controles reutilizados por hash. El último brazo quedó truncado y excluido de
comparaciones. No se completaron finalistas sintéticos, tres semillas ni control
de repetición. No se amplió el plazo ni se usó el test para elegir proporciones.
El informe `docs/reports/piloto_aumentacion_sintetica_exploratoria_2026-10-22.md`
reporta validación exploratoria, curvas, exposición y limitaciones. La evidencia
de cierre y del fallo original se conserva en `closure/` y `controller_failure.json`.

## Continuación autorizada (23 de octubre de 2026)

El usuario autorizó ampliar el presupuesto para confirmar finalistas sintéticos.
Se añaden 48 horas desde la preparación: 46 para entrenamiento y dos para evaluación.
La revisión `revisions/02_authorized_confirmation_20261023` preserva el cierre,
el presupuesto, el informe y el intento truncado anteriores. Se completa el
screening pendiente desde la inicialización original; se aplica la misma regla
de selección por validación para seis finalistas sintéticos, tres semillas
(4.000 pasos) y tres controles de repetición del ganador global por validación.
Los controles reales completos se reutilizan por hash. No cambia entrenador,
datos, receta ni calendario de LR; no hay nuevos renders. El test sigue siendo
de desarrollo y sus resultados reales ya conocidos no intervienen en selección.

## Cierre de la continuación (26 de octubre de 2026)

24 screenings y 18 finalistas sintéticos completados; 18 controles reales
reutilizados por hash. El primer control de repetición quedó truncado por plazo,
con último progreso persistido de 1.700/4.000 pasos; no se ejecutó evaluación
final del test de la extensión. La confirmación queda incompleta. El cierre
documental posterior al plazo usa solo artefactos existentes y conserva fallos.
Auditoría y comparaciones en `confirmation_closure_20261026/`; informe actualizado
en `docs/reports/piloto_aumentacion_sintetica_exploratoria_2026-10-22.md`.

## Finalización autorizada (26 de octubre de 2026)

El usuario solicitó completar los tres controles de repetición y la evaluación
final, ampliando el tiempo necesario. La revisión
`revisions/03_authorized_completion_20261026/` preserva el presupuesto, estado,
informe, fallos, locks y primer control incompleto anteriores. Los 24 screenings
y 36 finalistas completos se verifican por hash y se conservan.

`scripts/resume_augmentation_confirmation.py` ejecuta únicamente tres controles
de 4.000 pasos para la mezcla ya elegida por media de validación: 461 reales y
115 sintéticas con clásica. Sustituye las posiciones sintéticas por repeticiones
reales; comprueba las ocho secuencias y conserva las posiciones reales originales.
El intento parcial se archiva y comienza otra vez desde la inicialización común.
No cambia el entrenador, calendario de aprendizaje, semillas, datos ni receta.

Se reserva inicialmente un margen de siete días de pared, con las últimas dos
horas para evaluación, renovable dentro de esta autorización si las suspensiones
lo consumen. No se emplean las duraciones infladas por suspensión para omitir
controles pendientes. Mientras el proceso esté activo solicita al sistema evitar
la suspensión automática; no modifica ajustes permanentes ni impide la suspensión
manual. Una nueva ejecución debe comprobar antes procesos huérfanos y GPU libre.

Antes del test de desarrollo se congela un lock de 39 ejecuciones completas:
18 sintéticas, 18 controles reales y tres repeticiones. Se reutiliza el evaluador
congelado y se añaden contrastes directos de la mezcla contra repetición y contra
el control real de igual clásica, con semillas emparejadas y remuestreo de grupos.
El informe conserva el carácter exploratorio del test ya consultado. El cierre
requiere inspección de curvas/muestras, auditoría y entrega; iniciar el controlador
no constituye confirmación de una mejora.

El complemento `scripts/complete_augmentation_evaluation.py` usa las predicciones
persistidas y guarda su propia procedencia. El bootstrap original se conserva;
uno de sus sorteos omite la clase Madura y cambia el denominador del macro AP.
Los contrastes complementarios usan 200 sorteos comunes que contienen las tres
clases, registrando los rechazados. Sus intervalos quedan condicionados a esa
presencia y a las tres semillas ya entrenadas. Con solo seis grupos desiguales
no se afirma independencia entre sesiones ni significación confirmatoria.

## Cierre completo (26 de octubre de 2026)

Se completaron los tres controles a 4.000 pasos, verificando ocho secuencias y
8.000 posiciones emparejadas por semilla. El lock final incluye las 39 corridas
previstas y su evaluación de desarrollo; permanecen completos los 24 screenings.
Se revisaron curvas, predicciones, confusiones y contrastes directos. La mezcla
seleccionada (461 + 115, clásica) mejora +2,34 puntos de AP frente al control real
con clásica en las tres semillas; frente a repetición gana +0,88 puntos de media,
pero pierde en dos semillas. No queda confirmado un aporte consistente del
contenido sintético. Madura retrocede y debe revisarse en la siguiente iteración.

La evidencia de cierre está en `confirmation_evaluation_20261026/`; el informe
final mantiene los límites del test históricamente consultado, seis grupos y
cuatro plantas sintéticas. No se promovieron modelos ni se inició un nuevo piloto.
La auditoría adicional mencionada por el usuario sigue pendiente de ubicación;
se incorporará al diseño siguiente sin alterar esta campaña cerrada. El grafo
conserva sus diez errores de localizadores preexistentes, sin errores nuevos.

### Auditoría localizada después del cierre

Tras renovar la sesión GitHub, se recuperó la rama
`docs/auditoria-generacion-sintetica-20261025` en `939f94f`; el identificador
inicial `e3a4d29` no se resolvió. La
[revisión del 26 de octubre](../reports/revision_auditoria_para_siguiente_piloto_2026-10-26.md)
registra el contraste con el checkout actual y prioridades P0 para la nueva
versión. Se reprodujo el incumplimiento de un máximo reproductivo configurado en
cinco árboles Python. Ese máximo de cuatro deriva de una banda de objetos por
imagen y no constituye un límite botánico: la corrección indicada por el usuario
exige separar carga por planta y cantidad visible, permitiendo plantas con más
de diez frutos sin imponer un nuevo tope arbitrario. No se modificaron fuentes
ni resultados de la campaña cerrada.
