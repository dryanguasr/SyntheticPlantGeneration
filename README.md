<div align="center">

# SyntheticPlantGeneration
### Morfología procedural de uchuva, visión artificial y simulación robótica

**Python · Blender · Gazebo · percepción · evaluación reproducible**

[Arquitectura](docs/README.md) · [Resultados](docs/reports/indice_resultados_experimentales.md) · [Guías](docs/guides/) · [Documentación técnica](README_TECHNICAL.md)

</div>

## Propósito y estado

Plataforma de investigación sobre **uchuva (*Physalis peruviana*)**, datos
sintéticos y percepción para robótica agrícola. La estructura botánica se
representa como una morfología serializable; Blender y Gazebo la interpretan
para generar imágenes, anotaciones y escenarios de interacción.

**Corte documental: 24 de noviembre de 2026.** El repositorio reúne los avances
de generación, aumentación, segmentación, revisión de máscaras, localización y
modelo digital del cosechador. Los informes conservan resultados negativos y
pendientes. La transferencia al cultivo real, la madurez del fruto oculto y la
cosecha autónoma con percepción desplegable siguen sin demostrarse.

```text
Parámetros y reglas morfológicas
               │
               ▼
     Planta serializable
           ┌───┴────────┐
           ▼            ▼
        Blender       Gazebo
 imágenes / máscaras  escena / robot
```

## Tres frentes y sus componentes

| Frente | Código principal | Alcance documentado |
| --- | --- | --- |
| Morfología y generación sintética | [`src/uchuva_lsystem/`](src/uchuva_lsystem/) | Plantas nodales, escenas de cultivo, anotaciones, apariencia y validación geométrica |
| Aumentación y percepción | [`src/uchuva_classical_augmentation/`](src/uchuva_classical_augmentation/), [`src/uchuva_annotation_audit/`](src/uchuva_annotation_audit/) | Baselines, pilotos de detección y máscaras, aplicación de revisión y protocolos humanos |
| Simulación e interacción robótica | [`src/uchuva_gazebo/`](src/uchuva_gazebo/) | Captura, seguimiento, localización ArUco, robot paramétrico y demostraciones de cosecha |

La [documentación técnica](README_TECHNICAL.md) incluye también reconstrucción
desde vídeo real, Android, equipo, citación y organización del código.

## Resultados que orientan la lectura

- **Aumentación clásica v2:** 40 corridas confirmatorias válidas; ninguna receta
  superó todos los criterios operativos predeclarados. No se promovió una
  receta. [Cierre y controles](docs/reports/aumento_clasico_v2_confirmatory_2026-08-28.md).
- **Generación espacial:** veinte plantas admitidas; primer corte de 144 pares
  completos y continuación pausada con 503 vistas frente a la meta de 1.000.
  Las vistas repetidas no son plantas biológicamente independientes.
  [Generación y pilotos de detección](docs/reports/resultados_pilotos_deteccion_y_generacion_2026-11-24.md).
- **Segmentación de noviembre:** dos estudios de 18 corridas cada uno. El brazo
  de 240 exposiciones sintéticas mejoró 1,42 puntos de AP macro de máscaras en
  desarrollo histórico frente a su control real. Las referencias de entrenamiento
  son máscaras provisionales revisadas por el asistente; la adjudicación humana
  y la evaluación externa siguen pendientes.
  [Resultados, dosis y límites](docs/reports/resultados_segmentacion_privada_2026-11-24.md).
- **Cosechador V8:** se observaron nueve depósitos en una toma continua con
  movimiento prescrito. La respuesta de contacto del brazo, chasis y cultivo se
  omitió; la caída de los frutos liberados y sus contactos con la canasta sí se
  simularon. La admisión por fuerzas sigue pendiente y el diagnóstico RGB
  conservó 0/6 coincidencias. [Evidencia y condiciones](docs/reports/piloto_cad_v8_canasta_2026-11-24.md).

AP de cajas, AP de máscaras, seguimiento y errores métricos 3D corresponden a
protocolos distintos. Pintona, Madura y Sobremadura describen **apariencia del
capacho**, no madurez agronómica demostrada del fruto interno. El
[índice experimental](docs/reports/indice_resultados_experimentales.md) distingue
campañas cerradas, exploratorias y bloqueadas.

## Modelo digital y PhysalisHarvest

`RobotSpec` es la descripción canónica del robot; SDF, cinemática, límites y
validación consumen ese mismo modelo. El aporte de Diego de
[PhysalisHarvest](https://github.com/amayadiegoalejandro05/PhysalisHarvest)
se preserva en `contributions/physalisharvest/`, con procedencia y términos
originales. Un adaptador puro valida observaciones ópticas ArUco y una entrada
ROS usa una instalación común fuera del snapshot.

[Guía de integración](docs/guides/integracion_physalisharvest.md) ·
[Compatibilidad y verificaciones](docs/reports/conciliacion_cosechador_physalisharvest_2026-11-24.md).
TF calibrada, sincronización, puente de control/odometría e integración física
siguen pendientes; recibir una coordenada no confirma movimiento ni llegada.

## Explorar y reproducir

Desde la raíz, con un intérprete Python disponible:

```powershell
python scripts/generate_morphology_tree.py --seed 1
python scripts/validate_repository_context_graph.py
```

El núcleo morfológico no requiere Blender ni Gazebo. Los flujos de render,
visión, entrenamiento y simulación tienen entornos y activos específicos;
consultar las guías antes de iniciar una campaña.

- **Cultivo y banco de imágenes:** [generador y contrato Gazebo](docs/guides/generador_actual_y_contrato_gazebo.md), [continuación optimizada del dataset](docs/guides/completar_dataset_optimizado.md).
- **Máscaras y revisión humana:** [piloto de máscaras](docs/guides/piloto_privado_mascaras.md), [sintéticas y fotogramas](docs/guides/piloto_privado_sintetico_mascaras.md), [revisión cruzada](docs/guides/auditoria_ciega_segmentacion.md) y [manual para estudiantes](docs/guides/manual_estudiantes_revision_cruzada.pdf).
- **Robot y simulación:** [modelo paramétrico](docs/guides/robot_cosechador_parametrico.md), [demostración V8](docs/guides/piloto_cad_v8_canasta.md) y [piloto de cosecha histórico](docs/guides/piloto_cosecha_desmontable.md).
- **Otros consumidores:** [reconstrucción desde vídeo](docs/guides/reconstruccion_piloto.md), [Android y ArUco](docs/guides/aplicacion_movil_aruco.md).

## Procedencia y alcance

Los informes, código y tablas agregadas del proyecto se versionan. Datasets,
máscaras individuales, pesos, renders, vídeos, borradores y artículos
bibliográficos descargados permanecen fuera de Git. Un test consultado durante
desarrollo no recupera independencia al cambiarle el nombre.

El código original usa la [licencia MIT](LICENSE); las contribuciones, modelos,
datos y artículos conservan sus términos. La licencia institucional del aporte
PhysalisHarvest continúa pendiente y no se sustituye por MIT.

[Equipo y citación](README_TECHNICAL.md#equipo-y-citación) · [Detalle técnico](README_TECHNICAL.md) · [Referencias](docs/references/README.md) · [Contribuciones](contributions/README.md) · [Scripts](scripts/README.md)
