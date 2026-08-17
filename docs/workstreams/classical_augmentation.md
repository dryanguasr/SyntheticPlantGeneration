# Frente A: aumentacion clasica

Este frente contiene transformaciones convencionales de imagen y su evaluacion
como baseline frente a datos reales y sinteticos. No depende de Blender ni de
la morfologia procedural.

Estado actual:

- La entrega de Diego Amaya preservada en `contributions/diego_amaya/` aporta
  un lanzador multisemilla y configuraciones para E0, E1 y E2.
- E1 y E2 existen como datasets precomputados; sus recetas de transformacion
  no estan presentes en el codigo entregado.
- `src/uchuva_classical_augmentation/` registra esa limitacion para impedir
  que el repositorio atribuya reproducibilidad a operaciones no documentadas.

Cuando se recupere o implemente una receta, debe registrar semilla, padres de
cada muestra, parametros, version y hashes. Una derivacion de una foto real
no puede cruzar de `train` a `val` o `test`.
