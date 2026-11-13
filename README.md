<div align="center">

# SyntheticPlantGeneration
### Morfología procedural de uchuva, visión artificial y simulación robótica

**Python · Blender · Gazebo · computer vision · evaluación reproducible**

[Arquitectura](docs/README.md) · [Resultados](docs/reports/aumento_clasico_v2_confirmatory_2026-08-28.md) · [Guías](docs/guides/) · [Documentación técnica íntegra](README_TECHNICAL.md)

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
| Interpretación robótica | [`src/uchuva_gazebo/`](src/uchuva_gazebo/) | Escenas de percepción; la física de cosecha sigue pendiente |

## Hallazgo experimental que conviene conocer

La campaña confirmatoria de aumentación clásica v2 reunió **40 corridas válidas**. Algunas recetas mejoraron mAP50–95, pero ninguna superó **todos los criterios operacionales predeclarados**; no se promovió una nueva receta. La separación `train/val/test`, los fallos de ejecución detectados y la limitación de un test histórico previamente consultado están documentados.

[Leer el resultado negativo y sus métricas](docs/reports/aumento_clasico_v2_confirmatory_2026-08-28.md) · [Auditoría científica](docs/reports/auditoria_cientifica_blender_2026-09-08.md).

## Explorar el proyecto

```bash
# En un entorno con Python y dependencias configuradas
PYTHONPATH=src python scripts/generate_morphology_tree.py --seed 1
```

Los flujos de Blender, Gazebo y evaluación ML requieren dependencias y activos específicos. Ver [scripts](scripts/README.md), [generación de escenas](docs/guides/campo_gazebo.md) y [guía de revisión de resultados](docs/guides/revision_resultados_aumento_clasico_v2.md).

## Alcance honesto

- La morfología es una **hipótesis de modelado**, no una planta real medida exhaustivamente.
- La ejecución en Blender/Gazebo no implica validación de un cosechador físico.
- Los resultados negativos y los cambios de decisión se preservan como evidencia.
- Datasets, pesos, artículos y contribuciones de terceros **conservan sus licencias y autorías**; la [licencia del repositorio](LICENSE) no las reemplaza.

[Documentación técnica detallada anterior](README_TECHNICAL.md) · [Referencias y atribución](docs/references/README.md) · [Contribuciones externas](contributions/README.md).
