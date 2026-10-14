# Copas individuales frondosas

El preset `individual_dense_crown_v3` aumenta la ramificación y el follaje de
cada arbusto. Mantiene las posiciones del campo anterior: 1,4 m entre plantas
y 1,8 m entre hileras son supuestos históricos de esa escena. El usuario
observó aproximadamente 3 m o más entre plantas reales; este cambio no
recalibra distancias ni aumenta la densidad de plantación.

La fuente sigue siendo el árbol de `uchuva_lsystem`. Los tamaños foliares y
la política reproductiva conservan sus rangos; cambia el muestreo porque hay
más ramas. No se conserva el inventario del ensayo anterior. Los parámetros
son heurísticos y la semejanza botánica queda pendiente de revisión humana.

## Preparación y revisión

```powershell
.venv-training/Scripts/python.exe scripts/prepare_dense_crowns.py --source outputs/sparse_overhead_pilot_v7/scene_00/input.json --output outputs/dense_crowns_v3_final --workers 4
& 'C:/Program Files/Blender Foundation/Blender 5.1/blender.exe' -b -t 4 --python scripts/review_dense_crowns.py -- --source outputs/sparse_overhead_pilot_v7/scene_00/input.json --new outputs/dense_crowns_v3_final --output outputs/dense_crowns_v3_final/review_raw
```

Los directorios de preparación y render deben ser nuevos. `--plants` permite
una prueba pequeña; una exportación de campo debe usar las 36 plantas. La
revisión elige las plantas escasa, mediana y densa según el número de hojas
del campo anterior. Guarda frente/reverso con cámara ortográfica fija,
máscaras alfa de follaje y archivos Blender editables.

La cobertura es la fracción del encuadre fijo ocupada por hojas; **no** es
una tasa de oclusión. La superficie sumada de malla incluye las superficies
modeladas y no equivale automáticamente a área foliar biológica unilateral.

## Contactos y exportación

La resolución morfológica conserva órganos y permite solapamientos de proxies
hoja/hoja. Continúa corrigiendo los demás pares durante ocho iteraciones;
eso no garantiza resolver todos los conflictos. La auditoría de malla con
`tolerate_only_leaf_leaf=True` distingue intersecciones foliares toleradas
de otros conflictos. Los informes inválidos se conservan como tales.

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.1/blender.exe' -b -t 4 --python scripts/export_gazebo_field.py -- --input outputs/dense_crowns_v3_final/input.json --markers outputs/sparse_overhead_pilot_v7/markers --output outputs/gazebo/dense_crowns_v3 --individual-calyces
.venv-training/Scripts/python.exe scripts/check_dense_field.py --source outputs/sparse_overhead_pilot_v7/scene_00/input.json --new outputs/dense_crowns_v3_final --field outputs/gazebo/dense_crowns_v3
& 'C:/Program Files/Blender Foundation/Blender 5.1/blender.exe' -b --python scripts/audit_low_flight_clearance.py -- --field outputs/gazebo/dense_crowns_v3 --output outputs/gazebo/dense_crowns_v3/clearance.json
wsl -d Ubuntu-24.04 -- bash -lc 'cd /mnt/c/dev/SyntheticPlantGeneration && python3 scripts/inspect_dense_gazebo.py outputs/gazebo/dense_crowns_v3'
```

Cada capacho tiene identidad y modelo SDF propios; cada OBJ referencia un
catálogo de un material para evitar cargas cuadráticas de Assimp. Los postes
y cables superiores permanecen iguales; las cuerdas se vuelven a conectar
a nodos de las plantas regeneradas. No se añaden plántulas contextuales.

El video es una inspección con cámara móvil de Gazebo, no un vuelo físico.
La auditoría del pasillo usa todas las superficies originales y una envolvente
conservadora del Neo; no depende de contactos del motor físico. Un pasillo
bloqueado no autoriza retirar hojas. Las colisiones simplificadas del SDF no
certifican interacción física dentro de las copas ni operación del cosechador.

## Versión visual para memoria limitada

El campo detallado conserva las superficies de referencia. Si su carga no
cabe en memoria, generar un LOD por órgano, conservando IDs y materiales:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.1/blender.exe' -b -t 4 --python scripts/lod_dense_field.py -- --source outputs/gazebo/dense_crowns_v3 --output outputs/gazebo/dense_crowns_v3_lod
.venv-training/Scripts/python.exe scripts/check_dense_lod_silhouette.py --source outputs/gazebo/dense_crowns_v3 --lod outputs/gazebo/dense_crowns_v3_lod --input outputs/dense_crowns_v3_final/input.json
wsl -d Ubuntu-24.04 -- bash -lc 'cd /mnt/c/dev/SyntheticPlantGeneration && python3 scripts/inspect_dense_gazebo.py outputs/gazebo/dense_crowns_v3_lod'
```

La decimación se aplica individualmente, con un objetivo mínimo de 128
triángulos para órganos inicialmente grandes. Se conserva el original si
la caja cambia más de 2 mm; los órganos pequeños se copian completos. Esto
no certifica una distancia de Hausdorff de 2 mm. La correspondencia de todos
los objetos se comprueba; la revisión de siluetas exige IoU ≥0,95 y cambio
de cobertura ≤5 % en tres arbustos. La auditoría de vuelo sigue usando las
superficies completas, no el LOD.

`scripts/package_dense_review.py` reúne las tres plantas revisadas en un
Blender editable. Sus desplazamientos sirven para presentación y no son
las posiciones del campo.

El preset anterior y las políticas predeterminadas de exportación/auditoría
permanecen disponibles. No hay nuevas dependencias ni cambios del detector.
