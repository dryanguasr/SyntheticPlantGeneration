# Repositorio principal del robot y frontera con la generación sintética

El **25 de noviembre de 2026**, el usuario confirmó que
[Robot-Cosechador](https://github.com/dryanguasr/Robot-Cosechador) es el
repositorio principal del robot y autorizó conciliar allí su código y actualizar
`main`. La centralización anterior del PR 1 de SyntheticPlantGeneration se
conserva como antecedente; esta decisión cambia el lugar del desarrollo futuro.

| Responsabilidad | Repositorio canónico |
| --- | --- |
| Morfología de uchuva, parámetros, gramática e identidades de órganos | SyntheticPlantGeneration |
| Blender, generación de imágenes, aumentación, anotaciones y evaluación de datos | SyntheticPlantGeneration |
| Contrato de planta admitida y exportación de su evidencia | SyntheticPlantGeneration |
| Modelo del robot, perfiles, CAD, cinemática, planificación y control | Robot-Cosechador |
| Runtime y auditoría de cosecha, interfaces de hardware y adaptación ROS | Robot-Cosechador |

El robot usa `src/uchuva_robot/` y enlaza este generador como submódulo
`external/synthetic-plant-generation`, fijado inicialmente al commit
`5e74df79c040a06882f3e5a08a862f1d27a09c7b`. Un lock de revisión y hashes verifica
las entradas del proveedor. El generador no importa el repositorio del robot y
no adquiere una dependencia circular. Actualizar el proveedor exige revisar y
registrar el nuevo corte; la morfología no se redefine dentro del robot.

Las plantas se transfieren con unidades, semilla, preset, identidades, archivos
de origen y hashes explícitos. Los adaptadores del robot interpretan esa entrada
en metros. Un objetivo del simulador sigue siendo información privilegiada,
separada de la percepción desplegable.

## Continuidad de las fuentes históricas

Los módulos de robot de `src/uchuva_gazebo/`, sus scripts, perfiles,
`gazebo/harvest_system/` y el snapshot atribuido de PhysalisHarvest conservados
aquí forman parte de los experimentos ya registrados. Permanecen disponibles
para reproducibilidad y compatibilidad. Los cambios nuevos del robot se hacen
en Robot-Cosechador, no en dos copias activas.

La migración mantiene la autoría y los términos de origen y no mueve datasets,
pesos, CAD local, vídeos, renders ni evidencia privada al repositorio público de
generación. Tampoco convierte demostraciones cinemáticas, etiquetas sintéticas
o inspecciones estáticas en validación física o científica.

Para operación vigente, consultar el
[README principal del robot](https://github.com/dryanguasr/Robot-Cosechador) y su
[arquitectura](https://github.com/dryanguasr/Robot-Cosechador/blob/main/docs/arquitectura.md).
