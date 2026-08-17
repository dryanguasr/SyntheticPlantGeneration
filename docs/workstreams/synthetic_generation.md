# Frente B: generacion sintetica de uchuva

`src/uchuva_lsystem/` es la implementacion vigente. Su fuente de verdad es el
arbol morfologico serializable; Blender interpreta esa estructura para escena,
render y anotaciones. Los prototipos bajo `legacy/` se preservan como historia
y no definen la arquitectura actual.

Los contratos vigentes incluyen semillas reproducibles, procedencia explicita
de parametros, capacho cerrado con fruto oculto y una unica clase YOLO:
`calyx`. El frente tambien mantiene la calibracion de dominio y los
experimentos hibridos actuales, siempre con validacion y test reales aislados.
