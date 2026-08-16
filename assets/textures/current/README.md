# Texturas sintéticas de uchuva v3

Biblioteca generada de forma reproducible y sin depender de Blender.
Los colores inferidos del dataset son valores de dominio de cámara, no
mediciones espectrofotométricas de reflectancia intrínseca.

## Vista conjunta

![Albedo, venación por orden, normales y rugosidad](texture_contact_sheet.png)

Columnas: dos hojas, cuatro capachos verdes, tres pajizos y tres secos.
Filas: albedo, orden de venación, normal y rugosidad.

## Mapas por conjunto

### leaf_healthy

![Albedo](leaf_healthy_albedo.png) ![Normal](leaf_healthy_normal.png)

![Máscara de venas](leaf_healthy_vein_mask.png) ![Órdenes de venación](leaf_healthy_vein_debug.png)

### leaf_senescent

![Albedo](leaf_senescent_albedo.png) ![Normal](leaf_senescent_normal.png)

![Máscara de venas](leaf_senescent_vein_mask.png) ![Órdenes de venación](leaf_senescent_vein_debug.png)

### calyx_green_v0

![Albedo](calyx_green_v0_albedo.png) ![Normal](calyx_green_v0_normal.png)

![Máscara de venas](calyx_green_v0_vein_mask.png) ![Órdenes de venación](calyx_green_v0_vein_debug.png)

### calyx_green_v1

![Albedo](calyx_green_v1_albedo.png) ![Normal](calyx_green_v1_normal.png)

![Máscara de venas](calyx_green_v1_vein_mask.png) ![Órdenes de venación](calyx_green_v1_vein_debug.png)

### calyx_green_v2

![Albedo](calyx_green_v2_albedo.png) ![Normal](calyx_green_v2_normal.png)

![Máscara de venas](calyx_green_v2_vein_mask.png) ![Órdenes de venación](calyx_green_v2_vein_debug.png)

### calyx_green_v3

![Albedo](calyx_green_v3_albedo.png) ![Normal](calyx_green_v3_normal.png)

![Máscara de venas](calyx_green_v3_vein_mask.png) ![Órdenes de venación](calyx_green_v3_vein_debug.png)

### calyx_transition_v0

![Albedo](calyx_transition_v0_albedo.png) ![Normal](calyx_transition_v0_normal.png)

![Máscara de venas](calyx_transition_v0_vein_mask.png) ![Órdenes de venación](calyx_transition_v0_vein_debug.png)

### calyx_transition_v1

![Albedo](calyx_transition_v1_albedo.png) ![Normal](calyx_transition_v1_normal.png)

![Máscara de venas](calyx_transition_v1_vein_mask.png) ![Órdenes de venación](calyx_transition_v1_vein_debug.png)

### calyx_straw_v0

![Albedo](calyx_straw_v0_albedo.png) ![Normal](calyx_straw_v0_normal.png)

![Máscara de venas](calyx_straw_v0_vein_mask.png) ![Órdenes de venación](calyx_straw_v0_vein_debug.png)

### calyx_straw_v1

![Albedo](calyx_straw_v1_albedo.png) ![Normal](calyx_straw_v1_normal.png)

![Máscara de venas](calyx_straw_v1_vein_mask.png) ![Órdenes de venación](calyx_straw_v1_vein_debug.png)

### calyx_straw_v2

![Albedo](calyx_straw_v2_albedo.png) ![Normal](calyx_straw_v2_normal.png)

![Máscara de venas](calyx_straw_v2_vein_mask.png) ![Órdenes de venación](calyx_straw_v2_vein_debug.png)

### calyx_dry_v0

![Albedo](calyx_dry_v0_albedo.png) ![Normal](calyx_dry_v0_normal.png)

![Máscara de venas](calyx_dry_v0_vein_mask.png) ![Órdenes de venación](calyx_dry_v0_vein_debug.png)

### calyx_dry_v1

![Albedo](calyx_dry_v1_albedo.png) ![Normal](calyx_dry_v1_normal.png)

![Máscara de venas](calyx_dry_v1_vein_mask.png) ![Órdenes de venación](calyx_dry_v1_vein_debug.png)

### calyx_dry_v2

![Albedo](calyx_dry_v2_albedo.png) ![Normal](calyx_dry_v2_normal.png)

![Máscara de venas](calyx_dry_v2_vein_mask.png) ![Órdenes de venación](calyx_dry_v2_vein_debug.png)

## Regeneración

```powershell
python scripts/generate_uchuva_texture_library.py --seed 1701 --resolution 512
```

Los parámetros, estados de evidencia y hashes SHA-256 están en
`manifest.json`.
