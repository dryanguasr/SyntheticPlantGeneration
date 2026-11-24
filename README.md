<div align="center">

# SyntheticPlantGeneration
### Morfología procedural de uchuva, visión artificial y simulación robótica

**Python · Blender · Gazebo · computer vision · evaluación reproducible**

[Arquitectura](docs/README.md) · [Resultados](docs/reports/indice_resultados_experimentales.md) · [Guías](docs/guides/) · [Documentación técnica íntegra](README_TECHNICAL.md)

</div>

## ¿Qué problema aborda?

¿Puede una representación **morfológica trazable** de *Physalis peruviana* producir datos y escenarios útiles para percepción robótica? El proyecto separa la estructura de la planta de los motores que la visualizan: **Blender para generación de imágenes y anotaciones; Gazebo para escenarios de interacción y percepción**.

```text
Parámetros y reglas morfológicas
               │
               ▼
     Planta serializable
           ┌───┴────────┐
           ▼            ▼
        Blender       Gazebo
    imágenes / ML    escena / robot
```

## Tres frentes, un mismo núcleo

| Frente | Ruta | Estado verificado o pendiente |
| --- | --- | --- |
| Morfología procedural | [`src/uchuva_lsystem/`](src/uchuva_lsystem/) | Pipeline implementado; fidelidad botánica y transferencia por validar |
| Aumentación de datos | [`src/uchuva_classical_augmentation/`](src/uchuva_classical_augmentation/) | Baselines y protocolo confirmatorio reproducible |
| Interpretación robótica | [`src/uchuva_gazebo/`](src/uchuva_gazebo/) | Escenas de percepción y piloto de cosecha desmontable con ciclos auditados en un escenario rígido de Gazebo y posiciones conocidas |

## Modelo digital del cosechador y PhysalisHarvest

La rama `codex/integracion-physalisharvest-20261124` reúne el modelo CAD
paramétrico y el aporte ROS 2/ESP32 de Diego, preservado con su procedencia.
La descripción del robot sigue siendo `RobotSpec`; un adaptador puro valida
las observaciones ópticas ArUco y expone las interfaces pendientes.

[Guía de integración](docs/guides/integracion_physalisharvest.md) ·
[Compatibilidad y verificación](docs/reports/conciliacion_cosechador_physalisharvest_2026-11-24.md).
La integración operativa de TF, control y percepción queda pendiente; la rama
se entrega para revisión antes de fusionar a `main`.

## Hallazgo experimental que conviene conocer

La campaña confirmatoria de aumentación clásica v2 reunió **40 corridas válidas**. Algunas recetas mejoraron mAP50–95, pero ninguna superó **todos los criterios operacionales predeclarados**; no se promovió una nueva receta. La separación `train/val/test`, los fallos de ejecución detectados y la limitación de un test histórico previamente consultado están documentados.

[Leer el resultado negativo y sus métricas](docs/reports/aumento_clasico_v2_confirmatory_2026-08-28.md) · [Auditoría científica](docs/reports/auditoria_cientifica_blender_2026-09-08.md).

## Explorar el proyecto

```bash
# En un entorno con Python y dependencias configuradas
PYTHONPATH=src python scripts/generate_morphology_tree.py --seed 1
```

Los flujos de Blender, Gazebo y evaluación ML requieren dependencias y activos específicos. Ver [scripts](scripts/README.md), [generación de escenas](docs/guides/campo_gazebo.md) y [guía de revisión de resultados](docs/guides/revision_resultados_aumento_clasico_v2.md).

## Guías y evidencias por flujo

- **Generación espacial de uchuva.** [Generador y contrato de exportación a Gazebo](docs/guides/generador_actual_y_contrato_gazebo.md) y [resultados de la campaña de admisión espacial](docs/reports/plantas_admision_espacial_8h_2026-10-29.md).
- **Cosecha robótica simulada.** [Guía del piloto de cosecha desmontable](docs/guides/piloto_cosecha_desmontable.md) y [validación en Gazebo Harmonic](docs/reports/piloto_cosecha_desmontable_validacion_gazebo_2026-10-31.md).
- **Revisión cruzada de máscaras.** [Aplicación y protocolo de revisión](docs/guides/auditoria_ciega_segmentacion.md) y [manual ilustrado para estudiantes](docs/guides/manual_estudiantes_revision_cruzada.pdf).
- **Auditoría histórica.** [Revisión independiente del generador y de Gazebo sobre la versión `74b43d2`](docs/reports/auditoria_generacion_sintetica_2026-10-25.md).

## Alcance honesto

- La morfología es una **hipótesis de modelado**, no una planta real medida exhaustivamente.
- La ejecución en Blender/Gazebo no implica validación de un cosechador físico.
- Los resultados negativos y los cambios de decisión se preservan como evidencia.
- Datasets, pesos, artículos y contribuciones de terceros **conservan sus licencias y autorías**; la [licencia del repositorio](LICENSE) no las reemplaza.

[Documentación técnica detallada anterior](README_TECHNICAL.md) · [Referencias y atribución](docs/references/README.md) · [Contribuciones externas](contributions/README.md).
