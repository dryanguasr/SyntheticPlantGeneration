# Contribuciones preservadas

Esta carpeta conserva entregas externas o estudiantiles relevantes para el
proyecto sin confundirlas con la implementación vigente bajo `src/`.

Cada contribución debe incluir:

- autoría y procedencia;
- hash o referencia de la entrega recibida;
- alcance reproducible y limitaciones conocidas;
- exclusiones explícitas de datasets, pesos y resultados generados;
- licencia o estado de autorización cuando se conozca.

El código aquí preservado no define por sí solo la arquitectura morfológica de
uchuva. Las implementaciones vigentes permanecen en `src/uchuva_lsystem/`.

## Alcance de la licencia del repositorio

La licencia MIT situada en la raíz cubre el código original desarrollado para
este repositorio, salvo indicación explícita en contrario. **No relicencia
automáticamente** los snapshots estudiantiles o de terceros conservados en esta
carpeta.

Cada contribución mantiene su autoría y sus términos propios. Antes de
redistribuirla, publicarla o incorporarla al código MIT vigente debe verificarse
la autorización correspondiente y documentarse la decisión en su carpeta.

## PhysalisHarvest — banco de Diego

El snapshot íntegro en [`physalisharvest/`](physalisharvest/) conserva 107
archivos del corte `114ce5690e7bf024d57ce2c815b7f3afd1d82e38`, rama
`fix/2wd-bench-scripts`, del [repositorio de Diego](https://github.com/amayadiegoalejandro05/PhysalisHarvest).
Incluye los bancos ROS 2, firmware ESP32/DRV8833, herramientas y pruebas.
La centralización fue solicitada por el responsable de este repositorio el
24 de noviembre de 2026; se conservan los términos originales y el estado
«Licencia pendiente de decisión institucional», sin atribuirle MIT.

La [procedencia y hashes](physalisharvest.provenance.json) están fuera del
snapshot. Verificarlo con `python scripts/verify_physalisharvest_snapshot.py`
desde la raíz. La [guía de integración](../docs/guides/integracion_physalisharvest.md)
define cómo usar los paquetes directamente, sin mantener una copia adicional.
La arquitectura botánica y el modelo canónico del robot permanecen en `src/`.
