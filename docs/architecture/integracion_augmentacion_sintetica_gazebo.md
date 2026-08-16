# Arquitectura de aumentacion clasica, generacion sintetica y Gazebo

## Limites de responsabilidad

```text
                         Plant morphology JSON
                                   |
              +--------------------+-------------------+
              |                                        |
      Blender / vision dataset                 Gazebo export plan
              |                                        |
       synthetic perception                    robot simulation

classical augmentation ----------------> shared experiment protocol
```

- **Aumentacion clasica**: transforma fotografias reales y conserva el padre,
  la receta y la semilla de cada derivacion.
- **Generacion sintetica**: produce morfologia, escenas y anotaciones desde
  semillas, sin depender del frente clasico.
- **Gazebo**: consume solo la morfologia serializable y produce una
  representacion visual/fisica simplificada para simulacion.

Los frentes se comunican mediante archivos serializables, manifiestos y
scripts publicos; no mediante importaciones internas entre Blender, Gazebo y
las recetas clasicas.

## Contrato de trazabilidad para experimentos conjuntos

Cada muestra derivada debe identificar `sample_id`, `origin_group_id`, split,
hashes de imagen y etiqueta, dominio (`real`, `classical_augmented` o
`synthetic`) y transformacion o semilla de origen. Los splits se deciden por
`origin_group_id` antes de aumentar. `val` y `test` permanecen reales cuando
el estudio lo requiera.

## Puente de Gazebo

`uchuva_gazebo` no importa `bpy`, `gz`, ROS 2 ni Gazebo. Su interfaz estable
es `build_gazebo_export_plan(plant, config)`. El plan conserva IDs de
internodos, hojas, pedicelos y capachos para sensores, segmentacion y futuros
criterios de desprendimiento. Un escritor SDF y plugins de fisica se agregaran
solo despues de los spikes tecnicos definidos en
`plan_reestructuracion_augmentacion_sintetica_gazebo.md`.
