# Texturas sintéticas de uchuva v1

Biblioteca generada de forma reproducible y sin depender de Blender.
Los colores inferidos del dataset son valores de dominio de cámara, no
mediciones espectrofotométricas de reflectancia intrínseca.

## Vista conjunta

![Albedo, venación por orden, normales y rugosidad](texture_contact_sheet.png)

Columnas: `leaf_healthy`, `leaf_senescent`, `calyx_green`,
`calyx_straw`, `calyx_dry`. Filas: albedo, orden de venación, normal,
rugosidad.

## Mapas por conjunto

### leaf_healthy

![Albedo](leaf_healthy_albedo.png) ![Normal](leaf_healthy_normal.png)

![Máscara de venas](leaf_healthy_vein_mask.png) ![Órdenes de venación](leaf_healthy_vein_debug.png)

### leaf_senescent

![Albedo](leaf_senescent_albedo.png) ![Normal](leaf_senescent_normal.png)

![Máscara de venas](leaf_senescent_vein_mask.png) ![Órdenes de venación](leaf_senescent_vein_debug.png)

### calyx_green

![Albedo](calyx_green_albedo.png) ![Normal](calyx_green_normal.png)

![Máscara de venas](calyx_green_vein_mask.png) ![Órdenes de venación](calyx_green_vein_debug.png)

### calyx_straw

![Albedo](calyx_straw_albedo.png) ![Normal](calyx_straw_normal.png)

![Máscara de venas](calyx_straw_vein_mask.png) ![Órdenes de venación](calyx_straw_vein_debug.png)

### calyx_dry

![Albedo](calyx_dry_albedo.png) ![Normal](calyx_dry_normal.png)

![Máscara de venas](calyx_dry_vein_mask.png) ![Órdenes de venación](calyx_dry_vein_debug.png)

## Regeneración

```powershell
python scripts/generate_texture_assets.py --seed 1701 --resolution 512
```

Los parámetros, estados de evidencia y hashes SHA-256 están en
`manifest.json`.
