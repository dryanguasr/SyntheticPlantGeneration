# Modelo morfologico inicial de uchuva

Este documento resume el contrato botanico inicial del proyecto. La prioridad
es generar primero un arbol morfologico serializable y validable, y despues
interpretarlo como geometria en Blender.

## Estructura base

```text
Plant
  Axis / Branch
    Internode
    Node
      Leaf
      AxillaryBud
      ReproductiveUnit
        Pedicel
        Calyx
        Fruit
```

## Supuestos iniciales

- La planta se organiza por ejes, entrenudos y nodos.
- Las hojas estan asociadas a nodos, no a coordenadas globales arbitrarias.
- Las flores y frutos son solitarios y axilares.
- El pedicelo conecta el axil con la unidad reproductiva.
- En el preset de revisión `trained_trellis_pendulous_audit_v7`, la postura
  colgante del capacho se declara respecto a gravedad en el árbol, separada
  de la salida axilar del pedicelo. La inclinación numérica es una heurística
  pendiente de medición local; no una orientación universal de la especie.
- El caliz/capacho persistente acompana las etapas de fruto.
- Una misma planta puede mezclar yemas dormantes, ramas y estados reproductivos.
- La planta individual debe mantenerse moderadamente ramificada. La apariencia
  ancha o densa de cultivo debe resolverse en una capa superior de escena con
  varias plantas, no inflando un solo individuo.

## Parametros pendientes

Los rangos en `src/uchuva_lsystem/parameters.py` son valores
`manual_initial_guess` o `to_be_measured`. No deben tratarse como medidas
botanicas confirmadas.

## Criterios de validez

- Frutos y flores deben estar asociados a un nodo.
- Cada hoja debe pertenecer a un nodo.
- El pedicelo debe conectar el axil con la unidad reproductiva.
- Los frutos que requieren caliz deben tenerlo.
- El orden de ramas debe incrementar respecto al eje padre.
- El radio de ramas debe disminuir con el orden.
- La colision geometrica y la oclusion visual se evaluaran por separado.

## Escena de cultivo

La capa de escena debe mantenerse separada del L-System individual:

```text
CultivationScene
  PlantInstance 01
  PlantInstance 02
  PlantInstance 03
  Row / Bed
  Camera
  BackgroundCanopy
```

Presets iniciales:

- `single_plant_study`: una planta aislada para depurar morfologia.
- `foreground_plant_with_neighbors`: una planta principal con vecinas
  parciales para vision robotica.
- `row_canopy`: hilera/cama densa futura; no usar para calibracion inicial.

## Capacho

El capacho se modela con enfoque hibrido: geometria para la forma inflada y las
costillas principales, y material/textura para venacion secundaria y manchas.
Los campos minimos son `ribs`, `openness`, `inflation`, `fruit_visibility`,
`maturity` y `calyx_state`.

En la iteracion actual `openness` se fija en `0.0` para todos los capachos. El
fruto permanece en el arbol morfologico, pero queda oculto en la geometria de
Blender mientras se evalua si conviene modelar aperturas mas adelante.

## Fenología por cohortes v2

La interfaz `generate_morphology_tree` conserva `legacy_independent` como
comportamiento compatible cuando el argumento no se especifica. La ruta del
dataset v2 declara de forma explícita `phenology_model="literature_cohort_v1"`.

Este modelo ordena las unidades reproductivas por edad topológica. Las
posiciones antiguas tienden a estados maduros y las distales a flores o frutos
jóvenes. Se admite solapamiento entre estados vecinos, pero la validación
rechaza inversiones mayores a una etapa. Cada unidad puede serializar:

- cohorte de floración y rango ontogenético;
- rango estimado de días después de antesis;
- etapa principal BBCH;
- estado continuo de maduración del capacho;
- procedencia, incertidumbre y estado epistemológico.

La temperatura base, las tasas de aparición de nodos y el punto de quiebre del
modelo de Salazar se registran como prior diagnóstico. No aumentan por sí solos
el número de nodos renderizados. El preset del dataset usa un presupuesto
explícito de 16--17 nodos principales para conservar suficientes sitios después
de la primera bifurcación entre 8--12 nodos; esta es una hipótesis de
composición y permanece `manual_initial_guess`.

## Maduración conjunta del capacho

Los estados `inflated_green`, `transitioning_yellow`, `straw_yellow` y
`dry_deteriorated` se derivan del progreso continuo de maduración. El mismo
valor controla color, variante de textura, turgencia, inflación, área relativa,
circularidad, pubescencia, asimetría y pliegues localizados. El prior 45--90 DAA
reduce área proyectada relativa de 1,00 a 0,86 y circularidad de 0,59 a 0,39.
Estos extremos son referencias localizadas de literatura, no constantes
universales del cultivo colombiano.
