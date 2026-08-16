# Activos del proyecto

## Vigentes

`textures/current/` contiene la biblioteca de texturas cargada por Blender.
Corresponde al generador `0.5.0`: 14 conjuntos, incluido el estado de
transición verde--amarillo, con selección condicionada por madurez. Las
calibraciones históricas permanecen bajo `textures/legacy/`.

## Legado

`textures/legacy/uchuva_v1/` y `textures/legacy/uchuva_v2/` se conservan para
comparación. Ningún módulo vigente las carga por defecto.

La biblioteca activa se regenera con:

```powershell
python scripts\generate_uchuva_texture_library.py --seed 1701 --resolution 512
```
