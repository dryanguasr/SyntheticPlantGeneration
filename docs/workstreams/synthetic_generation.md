# Frente B: generacion sintetica de uchuva

`src/uchuva_lsystem/` es la implementacion vigente. Su fuente de verdad es el
arbol morfologico serializable; Blender interpreta esa estructura para escena,
render y anotaciones. Los prototipos bajo `legacy/` se preservan como historia
y no definen la arquitectura actual.

Los contratos vigentes incluyen semillas reproducibles, procedencia explicita
de parametros, capacho cerrado con fruto oculto y una unica clase YOLO:
`calyx`. El frente tambien mantiene la calibracion de dominio y los
experimentos hibridos historicos. La seleccion reciente se restringio a validacion,
pero el test real ya fue consultado durante el desarrollo: no es un holdout virgen.

La [auditoria cientifica del 8 de septiembre](../reports/auditoria_cientifica_blender_2026-09-08.md)
reconstruye tambien los artefactos locales posteriores al reporte de agosto.
El [plan de continuidad](../plan_auditoria_cientifica_blender_2026-09-08.md)
prioriza escenas de cultivo, localizacion 2D por instancia y etiquetas de maduracion
validables. `annotation_contract.py` prepara observaciones pendientes de revision;
todavia no promueve clases multiclase ni infiere madurez agronomica desde el capacho.
