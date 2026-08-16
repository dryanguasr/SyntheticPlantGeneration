# Legado

Nada bajo esta carpeta forma parte del pipeline vigente.

## Prototipos

- `prototypes/generic_blender_plant_v0_5.py`: generador geométrico recuperado.
- `prototypes/generic_blender_plant_v0_5.blend`: escena original.
- `prototypes/generic_blender_plant_v0_3_backup.blend1`: respaldo anterior.

## Scripts extraídos

- `extracted_scripts/generic_blender_plant_v0_5_extracted.py`.
- `extracted_scripts/generic_blender_plant_v0_3_backup_extracted.py`.

## Utilidades reemplazadas

- `scripts/deferred_batch_generation_stub.py`: stub sin implementación.
- `scripts/embed_legacy_posthoc_generator_in_blend.py`: empaquetaba el
  coordinador post hoc anterior y no contiene la arquitectura sincronizada.

## Documentos de migración

`migration/` conserva el prompt y el README anteriores a la reorganización.
Sirven como trazabilidad, no como instrucciones actuales.

El código vigente está exclusivamente en `src/uchuva_lsystem/`.
