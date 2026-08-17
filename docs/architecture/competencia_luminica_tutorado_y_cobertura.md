# Competencia lumínica, tutorado y cobertura de la copa

## Alcance

Esta iteración incorpora las observaciones agronómicas aportadas por Omar el
30 de julio de 2026:

- la copa se organiza en estratos bajo, medio y alto;
- las hojas buscan ocupar claros de luz a lo largo del día;
- el ápice y las ramas expanden una capa antes de recibir una guía ascendente;
- el tutorado aproxima una forma de trípode invertido;
- hojas de una misma planta y de plantas vecinas compiten por el espacio
  iluminado;
- el suelo y el fondo requieren gramíneas altas, kikuyo y malezas para evitar
  un fondo artificialmente despejado;
- la ruta normal de revisión debe usar EEVEE; Cycles queda como opción
  explícita mientras no produzca una ventaja observable.

La implementación es un primer modelo funcional-estructural auditable. No es
un cálculo calibrado de fotosíntesis, radiación o fisiología de
*Physalis peruviana*.

## Cadena morphology-first

```text
parámetros con procedencia
  → morfologías potenciales
  → expansión y guía contra trellis
  → postura foliar contra campo de luz compartido
  → árbol morfológico serializable
  → validación y métricas
  → geometría Blender
```

El nuevo `light_competition.py` no importa `bpy`. El campo de luz se resuelve
antes de crear la geometría y cada resultado queda almacenado en `Leaf`.

## Campo de luz estratificado

El modelo divide la copa en tres intervalos configurables:

- `lower`;
- `middle`;
- `upper`.

Para cada postura candidata de una hoja:

1. se aproxima su huella;
2. se proyecta la huella con cinco direcciones solares que representan
   mañana, transición, mediodía, transición y tarde;
3. se aproxima la incidencia entre el plano foliar y cada dirección solar;
4. se discretiza la proyección en celdas;
5. se mide cuántas celdas estaban libres;
6. se distingue el sombreo por hojas de la misma planta y por hojas de otras
   plantas;
7. se elige una postura que prioriza cobertura nueva e incidencia diaria,
   conserva un coste de
   deformación y evita contactos estructurales duros.

El solapamiento hoja-hoja continúa clasificado como `visual_occlusion`, no
como colisión geométrica. En una copa saturada puede ser correcto conservar
solapamiento visual.

Los campos serializados por hoja son:

- `canopy_stratum`;
- `daily_light_interception_proxy`;
- `projected_coverage_gain`;
- `intraspecific_shading_fraction`;
- `interspecific_shading_fraction`;
- `orientation_cost_terms`.

`daily_light_interception_proxy` no equivale a una tasa física de absorción.
Es la fracción ponderada de celdas proyectadas que la postura candidata ocupa
sin una reclamación previa relevante.

## Secuencia de tutorado

Las propuestas de rama usan dos fases:

### `stratum_expansion`

Mientras el alcance radial observado del estrato no supera su umbral
configurable, la rama recibe una preferencia hacia uno de tres brazos
deterministas. Los brazos están separados de manera aproximada y producen la
lectura de trípode invertido sin colocar ramas en coordenadas globales.

### `apical_lift_to_trellis`

Después de alcanzar el umbral de expansión, la dirección objetivo combina:

- componente vertical dominante;
- dirección hacia la línea de trellis inmediatamente superior;
- una corrección acotada de la dirección morfológica original.

La fase, el estrato y la dirección objetivo quedan en `Axis` y en
`ProposalDecision`.

## Densidad foliar

El preset `trained_trellis` aumenta de forma moderada:

- nodos potenciales del eje principal;
- probabilidad de ramificación por orden;
- presupuesto de longitud de ejes laterales;
- número máximo de entrenudos.

No se añaden hojas sueltas. Cada hoja continúa asociada a un nodo. La mayor
densidad proviene de más estructura nodal válida, veinte individuos en la
escena densa y una postura foliar que ocupa claros compartidos.

En el código se usa `leaf`/hoja porque la estructura actual representa hojas
simples asociadas a nodos; no se crean folíolos independientes.

## Vegetación acompañante

El entorno procedural crea tres perfiles visuales, todos etiquetados como
`background`:

- `lolium_perenne_like`: gramínea alta y estrecha;
- `kikuyu_like`: cobertura más baja y densa;
- `broadleaf_weeds_like`: malezas de hoja más ancha.

El sufijo `*_like` es intencional: describe una forma visual inicial, no una
reconstrucción taxonómica completa. Una fracción se concentra en la franja de
fondo para aportar el tono verde observado sin introducir falsas plantas de
uchuva ni nuevas clases de anotación.

El terreno usa además una textura verde procedural multiescala y, en los
modos de cultivo, un fondo cilíndrico distante con variación de pasto/maleza.
Ese fondo no contiene píxeles del dataset real. Su función es evitar cielo y
horizontes despejados detrás de la copa; la vegetación cercana continúa siendo
geometría explícita.

## Separación hoja–capacho y densidad de cultivo

La resolución global puede elevar una hoja entre 1,5 y 4,5 mm cuando su proxy
queda demasiado próximo a un capacho. El pecíolo conserva el nodo de origen y
el ajuste se serializa como `clearance_lift_cm` y
`clearance_lift_reason`. Una oclusión puramente proyectada sigue permitida y no
se confunde con interpenetración física.

Para capturas medias y de contexto se incluyen dos morfologías completas. Sus
hojas compiten en el mismo campo de luz y sus capachos visibles se anotan; no
se usan sustitutos low-poly ni se dejan frutos visibles sin etiqueta. Los
primeros planos grandes permanecen en una planta para conservar el contrato de
1–5 objetos.

La guía del tutor reduce a 30 % la curvatura residual de una rama ya dirigida.
Los dos primeros entrenudos comparten un corredor de unión con el eje padre;
esto evita interpretar la bifurcación botánica como una colisión consigo misma.

## Política de render

La ruta activa es:

```text
BLENDER_EEVEE_NEXT
```

Cambios:

- `standard_eevee` es el perfil predeterminado de aceptación humana;
- el piloto no genera Cycles salvo `--render-cycles`;
- el dataset usa `cycles_qa_count=0` por defecto;
- `photoreal_review` y `photoreal_final` se conservan para una futura decisión
  explícita;
- un baseline humano solo puede compararse con un candidato que use el mismo
  perfil de render.

## Procedencia y validación pendiente

Todos los valores nuevos están marcados como `engineering_heuristic`,
`manual_initial_guess` o `implementation_constraint`.

Antes de tratarlos como parámetros agronómicos se necesita:

1. medir alturas reales de los estratos y radios de expansión;
2. registrar el trazado solar y el manejo del lote objetivo;
3. medir cobertura foliar proyectada por estrato;
4. confirmar geometría, alturas y separaciones del sistema de tutorado;
5. comparar proporción de suelo/tallo visible en imágenes reales y sintéticas;
6. validar visualmente la mezcla y densidad de vegetación acompañante.
