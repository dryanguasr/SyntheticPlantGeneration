# SyntheticPlantGeneration: documentación técnica

Desde el **25 de noviembre de 2026**, el desarrollo canónico del robot y su
integración física se mantiene en
[Robot-Cosechador](https://github.com/dryanguasr/Robot-Cosechador). Las secciones
de cosechador de este documento conservan el corte histórico incorporado aquí;
el generador y su contrato de plantas siguen en este repositorio.
Véase [la separación de responsabilidades](docs/architecture/separacion_robot_cosechador.md).

Plataforma de investigación sobre **uchuva (*Physalis peruviana*)**, datos
sintéticos, percepción e interacción robótica. Este documento reúne el estado
por componente y la evidencia hasta el **24 de noviembre de 2026**. La
[entrada general](README.md) ofrece una síntesis y el
[índice experimental](docs/reports/indice_resultados_experimentales.md) organiza
los resultados por campaña.

El repositorio centraliza código y documentación de los frentes del proyecto.
La disponibilidad del código no implica que los datos, pesos, CAD originales o
artefactos locales acompañen a un clon, ni sustituye las validaciones pendientes.

## Equipo y citación

- David Yanguas-Rojas (autor principal del repositorio)
- Diego Alejandro Amaya Celis
- Laura Camila Rincón Malaver
- David Santiago Cruz Rodríguez
- Cristian Jimenez Morales
- Jhon Jaider Palencia Celis
- Breyner Felipe Galicia Gomez

Para citar el corte de software y resultados utilizado en el manuscrito:

> Yanguas-Rojas, D., Amaya Celis, D. A., y Rincón Malaver, L. C. (2026).
> *SyntheticPlantGeneration* [software]. GitHub.
> [Commit ec0d3a19f7a87ad5a7366ff75127be0dbd9a64f9](https://github.com/dryanguasr/SyntheticPlantGeneration/tree/ec0d3a19f7a87ad5a7366ff75127be0dbd9a64f9).

Ese identificador fija el corte del manuscrito; los avances posteriores tienen
sus propios commits e informes. Las [contribuciones](contributions/README.md)
conservan su autoría y sus términos originales.

## Arquitectura y responsabilidades

El modelo bajo `src/uchuva_lsystem/` es la fuente de la arquitectura botánica.
Blender y Gazebo interpretan una estructura serializable y validada. La
reconstrucción de superficies observadas es complementaria y no redefine esa
arquitectura. El robot tiene su propia descripción canónica, `RobotSpec`,
independiente de las plantas, el mundo y la selección de objetivos.

```text
Parámetros con procedencia → morfología → validación
                                          ├→ Blender → imágenes y anotaciones
                                          └→ Gazebo  → recorridos y captura
                                                         ↓
                                               percepción y seguimiento
                                                         ↓
                                              localización y evaluación 3D

RobotSpec → robot resuelto → cinemática / SDF / límites / control / auditoría
Vídeo real → reconstrucción parcial → revisión en Blender y Gazebo
```

| Componente | Código | Alcance documentado |
| --- | --- | --- |
| Aumentación clásica | `src/uchuva_classical_augmentation/` | Baselines E0/E1/E2 y campaña v2 reproducible, cerrada sin receta promovida |
| Generación sintética | `src/uchuva_lsystem/` | Morfología nodal, escenas de cultivo, geometría Blender, anotaciones, apariencia y validación |
| Revisión de anotaciones | `src/uchuva_annotation_audit/` | Aplicación de máscaras, revisión cruzada, asistencia interactiva y trazabilidad de decisiones |
| Simulación y percepción | `src/uchuva_gazebo/` | Campos SDF, captura, recorridos, seguimiento, localización ArUco y evaluación |
| Modelo digital del cosechador, corte histórico | `src/uchuva_gazebo/robot_spec.py`, `robot.py` y módulos asociados | Fuentes compatibles conservadas; desarrollo activo en Robot-Cosechador |
| Reconstrucción desde vídeo | `src/uchuva_reconstruction/` | Piloto COLMAP con superficies parciales importadas a Gazebo y Blender |
| Aplicación Android | `mobile/android/` | Detector histórico sin conexión y coordenadas sobre el plano de un ArUco; validación física pendiente |
| PhysalisHarvest y otros aportes | `contributions/` | Snapshots atribuidos; los bancos ROS 2/ESP32 se mantienen separados del núcleo morfológico |

La descripción detallada del generador y sus hipótesis se conserva en el código,
las guías y la [bibliografía](docs/references/README.md). Las pruebas geométricas
no demuestran por sí solas fidelidad botánica ni transferencia al campo.

## Resultados documentados por protocolo

AP de cajas, AP de máscaras, recall de localización 3D y éxito de una demostración
mecánica no son métricas intercambiables. Cada fila conserva sus condiciones de
adquisición, partición, selección y evaluación.

| Experimento | Resultado principal | Interpretación y evidencia |
| --- | --- | --- |
| Aumentación clásica v2, agosto | 40 corridas confirmatorias válidas; ninguna receta cumplió el criterio integral | No se promovió una receta; el test de esa campaña permaneció sin consultar. [Cierre](docs/reports/aumento_clasico_v2_confirmatory_2026-08-28.md) |
| Híbrido histórico, auditoría de septiembre | Δ medio de mAP50–95 de +0,001533 en tres semillas; dos deltas negativos | Evidencia exploratoria sobre test histórico consultado durante desarrollo. [Auditoría](docs/reports/auditoria_cientifica_blender_2026-09-08.md) |
| Reconstrucción real, 1 de octubre | Superficie frontal mejorada y cargada en Gazebo | Planta completa y escala física independiente no resueltas; métodos neurales no ejecutados. [Piloto](docs/reports/piloto_reconstruccion_uchuva_2026-10-01.md) |
| Segmentación, cierre del 4 de octubre | AP50–95 de máscaras del ciclo 3: 0,012271, frente a 0,001768 del ciclo 1 en su escenario final reservado | Mejora relativa con desempeño absoluto bajo. [Cierre](docs/reports/cierre_campana_segmentacion_2026-10-04.md) |
| Localización 3D, cierre del 5 de octubre | 37/388 capachos observables correctos; recall 9,54 %; precisión conjunta 80,43 % | No alcanzó el objetivo de cobertura y precisión. [Cierre](docs/reports/cierre_localizacion_3d_2026-10-05.md) |
| Vídeo continuo, cierre del 12 de octubre | Conciliación posterior: 62/388 correctos; recall 15,98 %; precisión conjunta 32,98 % | Ensayo retrospectivo en simulación; objetivo no alcanzado. [Evaluación](docs/reports/evaluacion_video_continuo_2026-10-08.md) |
| Plantas y banco espacial, octubre–noviembre | Veinte plantas admitidas; primer corte de 144 pares completos en seis escenas; continuación pausada con 503 vistas frente a 1.000 | Las vistas reutilizan órganos; la cobertura no mide eficacia de entrenamiento. [Síntesis](docs/reports/resultados_pilotos_deteccion_y_generacion_2026-11-24.md) |
| Detección con banco revisado de 115 sintéticas, 31 de octubre | AP macro de cajas: 18,83 % en control real con clásica y 20,89 % en mezcla; Sobremadura perdió 0,76 pp | Desarrollo histórico, tres semillas; la mejora macro no implica mejora en todas las clases. [Contrastes y controles](docs/reports/resultados_pilotos_deteccion_y_generacion_2026-11-24.md) |
| Segmentación privada, noviembre | Dos estudios de 18 corridas cada uno; 240 exposiciones sintéticas añadieron 1,42 pp de AP macro de máscaras en desarrollo frente al control | Referencias provisionales revisadas por el asistente; no validación humana independiente. [Informe](docs/reports/resultados_segmentacion_privada_2026-11-24.md) |
| Demostraciones CAD V8, 24 de noviembre | Nueve depósitos observados; repetición con codo arriba, tres frutos de cada arbusto | Movimiento prescrito, con respuesta de contacto de brazo, chasis y cultivo omitida. Admisión por fuerzas y autonomía pendientes. [Informe V8](docs/reports/piloto_cad_v8_canasta_2026-11-24.md) |

En el cuarto experimento de segmentación de octubre, procesar recortes elevó
el AP de máscaras del vuelo cercano de 0,010613 a 0,052503. El recall fue
22,62 %: todavía se omitía la mayoría de los capachos. Es una evaluación de
desarrollo distinta del escenario final reservado de los tres primeros ciclos.

En vídeo continuo se analizaron 7.972 pares RGB/máscara, con seis plantas
objetivo y doce de contexto. La conciliación posterior redujo duplicados de
78 a 15 y localizaciones correctas de 73 a 62. La precisión de asociación fue
48,94 %, distinta de la precisión conjunta que exige también exactitud espacial
y ausencia de duplicación. La captura a 30 Hz no demuestra inferencia en tiempo
real y las plantas objetivo ya habían sido inspeccionadas.

### Continuidad de percepción, apariencia y dataset

El diagnóstico iniciado como `outputs/integral_diagnosis_20261014` incorporó
comparaciones de percepción, ROI, seguimiento y pose mediante ArUco y movimiento
relativo. Su [registro de mejora integral](docs/reports/mejora_integral_2026-10-14.md)
termina con un cierre autorizado el 19 de octubre: diagnóstico, sin alcanzar el
objetivo científico. El [cierre y sucesor congelado](docs/reports/cierre_diagnostico_piloto_congelado_2026-10-19.md)
conserva resultados negativos y la continuidad correspondiente; la auditoría
inicial de octubre no se presenta como estado global actual del proyecto.

Las campañas posteriores comparan bancos sintéticos, aumentación clásica,
apariencia y exposición real emparejada. La
[síntesis de detección y generación](docs/reports/resultados_pilotos_deteccion_y_generacion_2026-11-24.md)
recoge tanto mejoras parciales como bloqueos por admisión física y regresiones
de Sobremadura. El cambio de textura, iluminación, cielos y clases no identifica
por separado el efecto causal de cada factor.

La continuación optimizada conserva los árboles admitidos, sus hashes y la
identidad de los órganos; cambia captura y condiciones documentadas. El banco
se pausó con 503 vistas, no se declara completada la meta de 1.000. Consultar
[la guía de continuación](docs/guides/completar_dataset_optimizado.md), la
[revisión del banco](docs/reports/diversidad_banco_500_2026-10-30.md) y los
[pilotos de apariencia](docs/guides/piloto_115_cielos_secado.md) antes de reanudar
cualquier ejecución.

### Máscaras, aplicación de revisión y pilotos privados

La aplicación permite delimitar, editar y revisar máscaras, conservar estados
inciertos, usar asistencia interactiva y exportar entregas. La
[revisión cruzada](docs/guides/auditoria_ciega_segmentacion.md) y su
[manual para estudiantes](docs/guides/manual_estudiantes_revision_cruzada.pdf)
separan lotes, revisores y adjudicación. Publicar estas herramientas no equivale
a contar con acuerdo humano medido ni con todas las etiquetas adjudicadas.

El [piloto de máscaras reales](docs/guides/piloto_privado_mascaras.md) usa
cohortes acumulativas de 20, 40, 80, 160, 320 y 461 fotos. Cada tamaño tiene
tres semillas, 4.000 actualizaciones y 8.000 exposiciones. El
[piloto con sintéticas y fotogramas](docs/guides/piloto_privado_sintetico_mascaras.md)
compara dosis de 120, 240 y 600 exposiciones sintéticas, un control de encuadre
y fotogramas reales por separado. Validación conserva 88 fotos y desarrollo
histórico 94; ese desarrollo ya había sido consultado en campañas anteriores.

Las máscaras privadas son referencias provisionales preparadas con propuestas
de detector y MobileSAM, revisadas por el asistente sobre RGB; el detector ya
había visto el entrenamiento histórico. No se usan como sustituto de una
adjudicación humana independiente. Las 50 fotos asignadas a revisión cruzada
forman parte del inventario de entrenamiento del piloto, sin reutilizar las
entregas estudiantiles como anotaciones de esa campaña.

Las [tablas agregadas](docs/reports/indice_resultados_experimentales.md) permiten
revisar AP, soporte, exposiciones y errores por semilla. Fotos, máscaras
individuales, pesos, predicciones y paquetes estudiantiles permanecen bajo
custodia separada. Los metadatos versionados de asistencia no incluyen los
pesos de MobileSAM ni cambian sus términos o los de Ultralytics.

## Modelo digital del cosechador y PhysalisHarvest

`robot-spec/1.0` describe el robot y resuelve un `ResolvedRobot` inmutable en SI,
con hash y procedencia. SDF, cinemática, marcos de herramienta, límites, control,
colisiones y auditoría consumen esa descripción. Las masas o dimensiones
estimadas no se convierten en mediciones del prototipo. El contrato actual del
brazo usa cinco ejes revolutos y rechaza brazos prismáticos antes de emitir
campos en radianes; las coordenadas prismáticas de mordaza y mecanismos pasivos
conservan metros.

El aporte de [PhysalisHarvest](https://github.com/amayadiegoalejandro05/PhysalisHarvest)
se preserva íntegro y atribuido bajo `contributions/physalisharvest/`. Sus dos
paquetes implementados son `bench_2wd` y `bench_2wd_drv8833`, con firmware y
herramientas de banco ESP32/DRV8833. El banco físico 2WD y el robot CAD son
plataformas distintas. El adaptador puro conserva el marco óptico, el tiempo y
los estados de la observación ArUco; no convierte un marcador superficial en
cáliz, baya o punto de corte.

La [entrada ROS canónica](docs/guides/integracion_physalisharvest.md) compila y
consulta esos nodos desde una instalación común bajo `outputs/`, sin copiar
paquetes ni cambiar el snapshot. Los lanzadores históricos Windows mantienen
sus rutas internas y no se anuncian como consumidores de esa instalación.
TF calibrada, sincronización RGB-D, adaptación Twist/controlador, odometría y
puente ROS/Gazebo continúan pendientes de integración operativa. Recibir una
coordenada, aceptar una orden y medir una llegada son hechos distintos.

Las demostraciones V8 mantienen objetivos preseleccionados por identidad y
movimiento prescrito. En la repetición con codo arriba se observaron nueve
cortes y nueve sueltas, con tres frutos de cada arbusto dentro de la canasta
tras el desplazamiento final a 501,236 s simulados. La gravedad y los contactos
de frutos liberados y canasta permanecen activos; la respuesta de contacto del
brazo, chasis y mallas estáticas del cultivo se omite. La holgura geométrica
certificada es acotada a los pares, exclusiones y trayectorias documentados,
sin validar por ello una misión autónoma controlada por fuerzas.

El diagnóstico de tres modelos RGB conservó **0/6 coincidencias** a confianza
0,25 e IoU 0,5. La visibilidad y la asociación de identidad del simulador son
información privilegiada; no acreditan percepción desplegable. El
[informe V8](docs/reports/piloto_cad_v8_canasta_2026-11-24.md), la
[conciliación de arquitecturas](docs/reports/conciliacion_cosechador_physalisharvest_2026-11-24.md)
y el [registro de correcciones](docs/reports/correcciones_revision_pr1_2026-11-24.md)
distinguen evidencia histórica, pruebas nuevas y pendientes.

## Etiquetas y límites científicos

- El baseline histórico conserva `{"calyx": 0}`. Los pilotos de detección y
  segmentación multiclase usan contratos separados de apariencia del capacho:
  Pintona —incluye verdes—, Madura y Sobremadura. Los IDs y diccionarios no se
  intercambian automáticamente.
- La apariencia del capacho no certifica la madurez agronómica del fruto oculto.
  `unknown`, incertidumbre y revisión humana pendiente permanecen explícitos.
- En los cierres históricos de localización, un acierto exige identidad y
  marcador correctos, error de posición ≤5 cm y ausencia de duplicación. Estima
  el centro del capacho, no la baya interna ni el punto de corte.
- En las campañas RGB, el estimador recibe imágenes, tiempos y calibración
  pública. Máscaras, identidades y poses verdaderas del simulador se reservan
  para evaluación o diagnósticos privilegiados, identificados como tales.
- Intersección geométrica, ocupación blanda y oclusión visual son conceptos
  distintos. La auditoría de mallas y el llenado de una caja no miden una tasa
  de oclusión.
- Las pruebas de software, renders y vuelos simulados no validan por sí solos
  fidelidad botánica, física de contacto, madurez o transferencia al campo.

Los siguientes hitos científicos son adjudicar categorías y máscaras con
personas, medir transferencia en sesiones reales independientes, verificar
incertidumbre y aislamiento de verdad en localización, completar cobertura y
escala de reconstrucción y admitir control e interacción físicos del robot.
El [plan científico](docs/plan_auditoria_cientifica_blender_2026-09-08.md) conserva
criterios y decisiones; sus estados históricos se leen junto a los cierres
posteriores y no como una única descripción del avance vigente.

## Organización y documentación

```text
src/uchuva_lsystem/                  morfología y pipeline Blender
src/uchuva_classical_augmentation/   baselines y aumentación clásica v2
src/uchuva_annotation_audit/         revisión y trazabilidad de máscaras
src/uchuva_gazebo/                   exportación, percepción, robot y evaluación
src/uchuva_reconstruction/           reconstrucción desde imágenes reales
mobile/android/                     aplicación experimental
configs/                            perfiles y configuraciones
scripts/                            entradas de generación y experimentos
tests/                              pruebas unitarias y de integración
docs/                               arquitectura, guías, informes y bibliografía
assets/                             activos y texturas
contributions/                      entregas externas atribuidas
legacy/                             prototipos históricos
outputs/                            artefactos locales fuera de Git
```

- [Documentación](docs/README.md), [scripts](scripts/README.md) y [activos](assets/README.md).
- [Campo Gazebo](docs/guides/campo_gazebo.md), [Neo aproximado](docs/guides/vuelo_neo_gazebo.md) y [vuelos entre hileras](docs/guides/vuelo_hileras_texturas.md).
- [Reconstrucción desde vídeo](docs/guides/reconstruccion_piloto.md) y [su informe](docs/reports/piloto_reconstruccion_uchuva_2026-10-01.md).
- [Android y validación](docs/guides/aplicacion_movil_aruco.md); código publicado sin APK ni pesos. La validación física permanece pendiente.
- [Revisión de aumentación clásica v2](docs/guides/revision_resultados_aumento_clasico_v2.md), [protocolo humano](docs/guides/protocolo_validacion_humana.md) y [preparación editorial](docs/guides/preparacion_redaccion_articulo.md).

Las guías describen pilotos fechados. Sus configuraciones, presupuestos y
comandos de entrenamiento o render no constituyen una autorización para iniciar
otra campaña.

## Empezar y verificar

El núcleo morfológico usa Python estándar. Desde la raíz:

```powershell
python scripts/generate_morphology_tree.py --seed 1
python scripts/validate_repository_context_graph.py
python scripts/verify_physalisharvest_snapshot.py
python scripts/physalisharvest_ros.py compilar --dry-run
```

El primer comando escribe `outputs/specs/morphology_tree_seed_1.json` y
`outputs/specs/validation_report_seed_1.json`. La inspección ROS no inicia nodos,
cámara, puertos ni motores. La compilación real y las consultas requieren el
entorno Jazzy descrito en la guía.

Para las pruebas del repositorio, usar un entorno con las dependencias de cada
componente ya configuradas:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -m unittest discover -s tests -v
```

La suite completa incluye visión y entrenamiento; no se limita a Python
estándar. Los contratos puros no requieren Blender ni Gazebo, mientras que la
generación y auditoría de mallas sí necesitan Blender y los ensayos nativos su
entorno de simulación. Una comprobación de código o un mock no se presenta como
ensayo físico. Los resultados de verificación pertenecen al corte de cada
informe; no se consideran ejecutados de nuevo al actualizar esta documentación.

### Compatibilidad con cortes anteriores

Se conservan perfiles y recetas históricas como
`E_plus_contact_policy_clearance`, `trained_trellis`,
`dense_trellis_synchronous`, `standard_eevee`, `literature_cohort_v1` y
`layered_understory_v2`. Sus comandos y referencias corresponden a sus
experimentos, no definen un único preset actual para todas las campañas.

El [resultado híbrido del 1 de agosto](docs/reports/resultado_dataset_hibrido_2026-08-01.md)
registró 0,690637 mAP50–95 frente a 0,682706 natural en ese experimento preliminar.
La auditoría posterior de tres semillas, citada arriba, impide presentarlo como
un ganador general. Entre los artefactos locales históricos están:

```text
outputs/current_review/uchuva_fidelity_competition_seed_025.blend
outputs/datasets/uchuva_original_synthetic_seed_1000_v1/
outputs/experiments/checkpoint_interpolation_scale80_seed_1000_v1/interpolated_checkpoints/natural_hybrid_alpha_045.pt
outputs/human_validation/
outputs/archive/
```

Esas rutas ayudan a interpretar informes antiguos; sus archivos no acompañan
necesariamente al repositorio. La guía correspondiente fija el perfil, los
activos, el entorno y los hashes antes de reproducir un experimento.

## Procedencia, conservación y licencia

`AGENTS.md` es la autoridad prescriptiva y
`docs/repository_context_graph.json` describe subsistemas y evidencia. El
prototipo genérico de `legacy/` no es el modelo botánico vigente. Cada ejecución
registra versión, semilla, preset, configuración y procedencia.

`Dataset Original/` es de solo lectura. Las particiones y el uso de evaluación
se declaran por campaña; un conjunto histórico consultado durante desarrollo
no se vuelve independiente al renombrarlo o cambiar un lock. Las nuevas vistas
de la misma planta tampoco se cuentan como muestras biológicas independientes.

Se versionan los informes propios, guías, código, metadatos bibliográficos y
tablas agregadas. Fotos y máscaras individuales, datasets, pesos, renders,
vídeos, salidas de entrenamiento, `docs/drafts/`, referencias brutas y PDFs de
artículos permanecen fuera de Git. Los enlaces a `outputs/` requieren los
artefactos locales correspondientes. Los manuales propios del proyecto pueden
publicarse como documentos; no se confunden con copias de artículos de terceros.
Se preservan fallos y resultados negativos junto a los cierres.

El código original usa la [licencia MIT](LICENSE), salvo indicación explícita
en contrario. Esto no relicencia contribuciones estudiantiles o de terceros,
datasets, pesos, modelos ni artículos. La licencia institucional del snapshot
PhysalisHarvest continúa pendiente; sus archivos conservan términos y autoría.
Consultar [contribuciones](contributions/README.md) y
[referencias](docs/references/README.md) para condiciones y atribuciones.
